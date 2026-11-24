# Speaker on Sindoh printers that have one (3DWOX 1X): tones, tunes and the
# printer's own voice files.
#
# The 1X's speaker is a USB sound card with its own amplifier (GPIO 180),
# played by Sindoh's /bin/mplayer on the stock side; Klipper runs in a
# chroot that has neither the sound device nor a player. So this module
# only leaves a request: it writes a tone or tune as a WAV file into
# REQUEST_DIR and the line "wav NAME" (or "tts LANG/FILE", "file NAME") into
# REQUEST_DIR/request. The stock-side helper (sindoh-klipper
# install/x1/x1_web.sh, "soundd") plays it with the amplifier on, then
# switches the amplifier off. Nothing here blocks the reactor for long: a
# note is one period of samples repeated.
#
#   [sindoh_sound]
#   #request_dir: /run/dp200/sound
#   #volume: 0.5            # 0..1, default for every command
#
#   PLAY_TONE [FREQ=880] [MS=200] [VOLUME=]
#   PLAY_TUNE NOTES="C5:200 E5:200 G5:400 R:100 C6:300" [VOLUME=]
#       note names C..B with # or b and an octave (A4 = 440 Hz), or a
#       frequency in Hz; R is a rest; the number after ":" is milliseconds
#   PLAY_SOUND FILE=NAME          a WAV/MP3 in printer_data/config/sounds/
#   PLAY_SOUND TTS=eng/NAME.mp3   one of Sindoh's voice files (/app/TTS)
#
# Copyright (C) 2026  This file may be distributed under the terms of the
# GNU GPLv3 license.
import logging, math, os, re, struct, time

RATE = 22050
NOTES = {'C': -9, 'D': -7, 'E': -5, 'F': -4, 'G': -2, 'A': 0, 'B': 2}
MAX_MS = 20000


def note_freq(name):
    m = re.match(r'^([A-Ga-g])([#b]?)(-?\d)$', name)
    if not m:
        return float(name)
    n = NOTES[m.group(1).upper()] + {'#': 1, 'b': -1, '': 0}[m.group(2)]
    return 440. * 2. ** ((n + 12 * (int(m.group(3)) - 4)) / 12.)


def tone_bytes(freq, ms, volume):
    count = int(RATE * ms / 1000.)
    if freq <= 0 or count <= 0:
        return b'\0\0' * max(count, 0)
    period = max(2, int(round(RATE / freq)))
    amp = int(32000 * volume)
    one = b''.join(struct.pack('<h', int(amp * math.sin(2 * math.pi * i / period)))
                   for i in range(period))
    reps = count // period
    # whole periods only (each ends at zero: no click), then silence
    return one * reps + b'\0\0' * (count - reps * period)


class SindohSound:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.dir = config.get('request_dir', '/run/dp200/sound')
        self.volume = config.getfloat('volume', 0.5, minval=0., maxval=1.)
        self.seq = 0
        gcode = self.printer.lookup_object('gcode')
        for name in ('PLAY_TONE', 'PLAY_TUNE', 'PLAY_SOUND'):
            gcode.register_command(name, getattr(self, 'cmd_' + name),
                                   desc=getattr(self, 'cmd_%s_help' % name))

    def get_status(self, eventtime):
        # (also makes "'sindoh_sound' in printer" work in macros)
        return {'volume': self.volume}

    def _request(self, line):
        try:
            os.makedirs(self.dir, exist_ok=True)
            tmp = os.path.join(self.dir, '.request.tmp')
            with open(tmp, 'w') as f:
                f.write(line + '\n')
            os.rename(tmp, os.path.join(self.dir, 'request'))
        except OSError as e:
            raise self.printer.command_error("Sound request failed: %s" % e)

    def _play_wav(self, data):
        self.seq = (self.seq + 1) % 1000
        name = 'snd%03d.wav' % self.seq
        path = os.path.join(self.dir, name)
        try:
            os.makedirs(self.dir, exist_ok=True)
            # old generated files: keep the last few only
            for old in os.listdir(self.dir):
                if old.startswith('snd') and old != name:
                    p = os.path.join(self.dir, old)
                    if time.time() - os.path.getmtime(p) > 60:
                        os.remove(p)
            with open(path, 'wb') as f:
                f.write(b'RIFF' + struct.pack('<I', 36 + len(data)) + b'WAVE'
                        + b'fmt ' + struct.pack('<IHHIIHH', 16, 1, 1, RATE,
                                                RATE * 2, 2, 16)
                        + b'data' + struct.pack('<I', len(data)) + data)
        except OSError as e:
            raise self.printer.command_error("Sound file failed: %s" % e)
        self._request('wav ' + name)

    def _volume(self, gcmd):
        return gcmd.get_float('VOLUME', self.volume, minval=0., maxval=1.)

    cmd_PLAY_TONE_help = "Play a tone on the speaker: FREQ= (Hz) MS= VOLUME="
    def cmd_PLAY_TONE(self, gcmd):
        freq = gcmd.get_float('FREQ', 880., minval=20., maxval=10000.)
        ms = gcmd.get_int('MS', 200, minval=10, maxval=MAX_MS)
        self._play_wav(tone_bytes(freq, ms, self._volume(gcmd)))

    cmd_PLAY_TUNE_help = 'Play notes on the speaker: NOTES="C5:200 R:100 G5:400" VOLUME='
    def cmd_PLAY_TUNE(self, gcmd):
        vol = self._volume(gcmd)
        data, total = [], 0
        for tok in gcmd.get('NOTES').split():
            name, _, ms = tok.partition(':')
            try:
                ms = int(ms or 200)
                freq = 0. if name.upper() == 'R' else note_freq(name)
            except ValueError:
                raise gcmd.error("PLAY_TUNE: can't read note '%s'" % tok)
            total += ms
            if total > MAX_MS:
                raise gcmd.error("PLAY_TUNE: longer than %d s" % (MAX_MS // 1000))
            data.append(tone_bytes(freq, ms, vol))
            data.append(tone_bytes(0, 15, vol))   # a gap between notes
        self._play_wav(b''.join(data))

    cmd_PLAY_SOUND_help = "Play a sound file: FILE= (config/sounds) or TTS=eng/NAME.mp3"
    def cmd_PLAY_SOUND(self, gcmd):
        tts = gcmd.get('TTS', None)
        name = tts if tts is not None else gcmd.get('FILE')
        if not re.match(r'^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)?$', name) or '..' in name:
            raise gcmd.error("PLAY_SOUND: bad file name '%s'" % name)
        self._request(('tts ' if tts is not None else 'file ') + name)


def load_config(config):
    return SindohSound(config)
