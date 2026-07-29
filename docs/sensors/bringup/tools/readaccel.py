import struct, subprocess, sys, os
D='/sys/bus/iio/devices/iio:device2'
scale=float(open(D+'/in_accel_scale').read())
for e in os.listdir(D+'/scan_elements'):
    if e.endswith('_en'): open(D+'/scan_elements/'+e,'w').write('1')
open(D+'/buffer/length','w').write('128')
open(D+'/buffer/enable','w').write('1')
f=open('/dev/iio:device2','rb')
print("scale = %g  (raw -> m/s^2)" % scale)
print("      x        y        z     |g|")
for i in range(8):
    d=f.read(24)
    x,y,z=struct.unpack_from('<iii',d,0)
    ts,=struct.unpack_from("<q",d,16)
    ax,ay,az=x*scale,y*scale,z*scale
    print("  %7.3f  %7.3f  %7.3f   %5.3f m/s^2" % (ax,ay,az,(ax*ax+ay*ay+az*az)**0.5))
f.close()
open(D+'/buffer/enable','w').write('0')
