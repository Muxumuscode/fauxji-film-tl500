"""Manual-meter bias (fauxji_rot MDEV_AT): runs the patched words of a built .elf in the small ARM interpreter of test_sky.py.

    python tools/test_meter.py <built EX1-DSP-SR-008264.elf>

In manual mode the meter must read the biased exposure as 0 (deviation + AE_BIAS); in every other mode the deviation passes through.
Both meter read-outs must call the wrapper."""
import os, sys, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_sky as T
import fauxji_rot as R
import fauxji_ui as ui

d = open(sys.argv[1], 'rb').read()
B = R.B
blob = d[R.MDEV_AT - B:R.MDEV_END - B]
bad = 0
for site in R.METER_SITES:
    w = struct.unpack_from('<I', d, site - B)[0]
    if w != ui._b(site, R.MDEV_AT, link=True):
        print('meter call at %x does not reach the wrapper' % site); bad += 1
for dev in (-40, -8, -5, -3, 0, 2, 5, 33):
    for manual in (0, 1):
        c = T.CPU([(R.MDEV_AT, blob)])
        c.stubs[R.DEV_GET] = lambda cpu, v=dev: cpu.r.__setitem__(0, v & 0xFFFFFFFF)
        c.stubs[R.IS_MANUAL] = lambda cpu, m=manual: cpu.r.__setitem__(0, m)
        c.r[4] = 0x44
        c.run(R.MDEV_AT, ret=0xDEAD0000)
        got = c.r[0] - (1 << 32) if c.r[0] & 0x80000000 else c.r[0]
        want = dev + (R.AE_BIAS if manual else 0)
        if got != want or c.r[4] != 0x44 or c.r[13] != 0x10000000:
            print('dev %d manual %d -> %d (want %d)' % (dev, manual, got, want)); bad += 1
print('manual meter wrapper: bad', bad)
