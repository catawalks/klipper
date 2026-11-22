# Feed filament until a sensor changes (load and unload routines)
#
# Copyright (C) 2026  catawalks
#
# This file may be distributed under the terms of the GNU GPLv3 license.
#
# [feed_until NAME]
# pin:       the sensor, read as an endstop ("triggered" = filament there)
# steppers:  every extruder stepper this sensor may have to stop, by name:
#            "extruder" and/or the NAME of an [extruder_stepper NAME]
#
# FEED_UNTIL SENSOR=NAME DISTANCE=<mm> [STATE=1] [STEPPERS=a,b] [SPEED=]
#            [ACCEL=] [REQUIRE=1]
#   Moves the listed steppers together by up to DISTANCE (negative pulls
#   back) and stops them in the micro-controller the moment the sensor
#   reads STATE (1 = filament there, 0 = gone). With REQUIRE=1 it is an
#   error if the sensor has not changed by the end of the move. The
#   steppers are taken off their extruder for the move and put back
#   afterwards. The sensor pin may also be used by a
#   [filament_switch_sensor] (write it with the same "!" there).
import logging
from . import force_move

class FeedUntil:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.name = config.get_name().split()[-1]
        ppins = self.printer.lookup_object('pins')
        pin = config.get('pin')
        ppins.allow_multi_use_pin(pin.replace('!', '').replace('^', '')
                                  .replace('~', '').strip())
        self.mcu_endstop = ppins.setup_pin('endstop', pin)
        self.stepper_names = [n.strip() for n in
                              config.get('steppers').split(',') if n.strip()]
        if not self.stepper_names:
            raise config.error("feed_until needs at least one stepper")
        self.velocity = config.getfloat('velocity', 5., above=0.)
        self.accel = config.getfloat('accel', 0., minval=0.)
        self.esteppers = {}
        self.active = []
        self.homing_accel = 0.
        self.next_cmd_time = 0.
        self.commanded_pos = 0.
        self.last_distance = 0.
        self.last_stopped = False
        self.motion_queuing = self.printer.load_object(config, 'motion_queuing')
        self.trapq = self.motion_queuing.allocate_trapq()
        self.trapq_append = self.motion_queuing.lookup_trapq_append()
        self.printer.load_object(config, 'homing')
        self.printer.register_event_handler('klippy:mcu_identify',
                                            self._handle_mcu_identify)
        gcode = self.printer.lookup_object('gcode')
        gcode.register_mux_command('FEED_UNTIL', 'SENSOR', self.name,
                                   self.cmd_FEED_UNTIL,
                                   desc=self.cmd_FEED_UNTIL_help)
    def _handle_mcu_identify(self):
        for name in self.stepper_names:
            if name == 'extruder' or (name.startswith('extruder')
                                      and name[8:].isdigit()):
                extruder = self.printer.lookup_object(name, None)
                es = getattr(extruder, 'extruder_stepper', None)
            else:
                es = self.printer.lookup_object('extruder_stepper ' + name,
                                                None)
                es = getattr(es, 'extruder_stepper', None)
            if es is None:
                raise self.printer.config_error(
                    "feed_until %s: unknown extruder stepper '%s'"
                    % (self.name, name))
            self.esteppers[name] = es
            self.mcu_endstop.add_stepper(es.stepper)
    def get_status(self, eventtime):
        return {'last_distance': self.last_distance,
                'last_stopped': self.last_stopped}
    def _query(self):
        toolhead = self.printer.lookup_object('toolhead')
        print_time = toolhead.get_last_move_time()
        return bool(self.mcu_endstop.query_endstop(print_time))
    cmd_FEED_UNTIL_help = "Feed filament until a sensor changes"
    def cmd_FEED_UNTIL(self, gcmd):
        dist = gcmd.get_float('DISTANCE')
        want = bool(gcmd.get_int('STATE', 1, minval=0, maxval=1))
        speed = gcmd.get_float('SPEED', self.velocity, above=0.)
        accel = gcmd.get_float('ACCEL', self.accel, minval=0.)
        require = gcmd.get_int('REQUIRE', 0)
        names = [n.strip() for n in
                 gcmd.get('STEPPERS', ','.join(self.stepper_names)).split(',')
                 if n.strip()]
        for name in names:
            if name not in self.esteppers:
                raise gcmd.error("'%s' is not in the steppers of feed_until %s"
                                 % (name, self.name))
            if not name.startswith('extruder'):
                continue
            heater = self.printer.lookup_object(name).get_heater()
            if not heater.can_extrude:
                raise gcmd.error("FEED_UNTIL: %s is below its minimum"
                                 " extrude temperature" % (name,))
        toolhead = self.printer.lookup_object('toolhead')
        toolhead.wait_moves()
        self.last_distance = 0.
        self.last_stopped = False
        if not dist or self._query() == want:
            self.last_stopped = self._query() == want
            gcmd.respond_info("feed_until %s: sensor already %s, no move"
                              % (self.name, "triggered" if want else "open"))
            return
        esteppers = [self.esteppers[n] for n in names]
        toolhead.flush_step_generation()
        self.active = [es.stepper for es in esteppers]
        saved = [(es, es.motion_queue) for es in esteppers]
        start = [(s, s.get_mcu_position()) for s in self.active]
        self.commanded_pos = 0.
        for s in self.active:
            s.set_trapq(self.trapq)
            s.set_position([0., 0., 0.])
        self.motion_queuing.check_step_generation_scan_windows()
        stepper_enable = self.printer.lookup_object('stepper_enable')
        stepper_enable.set_motors_enable([s.get_name() for s in self.active],
                                         True)
        self.homing_accel = accel
        phoming = self.printer.lookup_object('homing')
        try:
            phoming.manual_home(self, [(self.mcu_endstop, self.name)],
                                [dist, 0., 0., 0.], speed,
                                False, want, False)
        finally:
            toolhead.flush_step_generation()
            s, start_pos = start[0]
            moved = (s.get_mcu_position() - start_pos) * s.get_step_dist()
            if s.get_dir_inverted()[0]:
                moved = -moved
            self.last_distance = moved
            for es, queue in saved:
                if queue:
                    es.sync_to_extruder(queue)
                else:
                    es.stepper.set_trapq(None)
            self.motion_queuing.check_step_generation_scan_windows()
            self.active = []
            self.sync_print_time()
        self.last_stopped = self._query() == want
        gcmd.respond_info("feed_until %s: moved %.1f mm, sensor %s"
                          % (self.name, self.last_distance,
                             "changed" if self.last_stopped else "NOT changed"))
        if require and not self.last_stopped:
            raise gcmd.error("FEED_UNTIL %s: the sensor did not change within"
                             " %.0f mm" % (self.name, abs(dist)))
    # Toolhead wrappers to support homing (as in manual_stepper.py)
    def sync_print_time(self):
        toolhead = self.printer.lookup_object('toolhead')
        print_time = toolhead.get_last_move_time()
        if self.next_cmd_time > print_time:
            toolhead.dwell(self.next_cmd_time - print_time)
        else:
            self.next_cmd_time = print_time
    def flush_step_generation(self):
        toolhead = self.printer.lookup_object('toolhead')
        toolhead.flush_step_generation()
    def get_position(self):
        return [self.commanded_pos, 0., 0., 0.]
    def set_position(self, newpos, homing_axes=""):
        self.flush_step_generation()
        self.commanded_pos = newpos[0]
        for s in self.active:
            s.set_position([self.commanded_pos, 0., 0.])
    def get_last_move_time(self):
        self.sync_print_time()
        return self.next_cmd_time
    def dwell(self, delay):
        self.next_cmd_time += max(0., delay)
    def drip_move(self, newpos, speed, drip_completion):
        self.sync_print_time()
        start_time = self.next_cmd_time
        cp = self.commanded_pos
        axis_r, accel_t, cruise_t, cruise_v = force_move.calc_move_time(
            newpos[0] - cp, speed, self.homing_accel)
        self.trapq_append(self.trapq, start_time,
                          accel_t, cruise_t, accel_t,
                          cp, 0., 0., axis_r, 0., 0.,
                          0., cruise_v, self.homing_accel)
        self.commanded_pos = newpos[0]
        end_time = start_time + accel_t + cruise_t + accel_t
        self.motion_queuing.drip_update_time(start_time, end_time,
                                             drip_completion)
        self.motion_queuing.wipe_trapq(self.trapq)
    def get_kinematics(self):
        return self
    def get_steppers(self):
        return list(self.active)
    def calc_position(self, stepper_positions):
        return [stepper_positions[self.active[0].get_name()], 0., 0.]

def load_config_prefix(config):
    return FeedUntil(config)
