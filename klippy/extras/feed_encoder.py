# A filament motion pick-up, watched by feed_until for jams
#
# Copyright (C) 2026  catawalks
#
# This file may be distributed under the terms of the GNU GPLv3 license.
#
# [feed_encoder NAME]
# pin:           the pick-up; every change of its level is counted
# jam_distance:  mm the motors may feed with no change before FEED_UNTIL
#                (ENCODER=NAME) stops with a "filament not moving" error

class FeedEncoder:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.name = config.get_name().split()[-1]
        self.jam_distance = config.getfloat('jam_distance', 30., above=0.)
        self.count = 0
        self.last_eventtime = 0.
        buttons = self.printer.load_object(config, 'buttons')
        buttons.register_buttons([config.get('pin')], self._handle_change)
    def _handle_change(self, eventtime, state):
        self.count += 1
        self.last_eventtime = eventtime
    def get_status(self, eventtime):
        return {'count': self.count}

def load_config_prefix(config):
    return FeedEncoder(config)
