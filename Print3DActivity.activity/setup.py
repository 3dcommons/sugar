#!/usr/bin/env python
try:
	from sugar.activity import bundlebuilder
	bundlebuilder.start()
except ImportError:
	import os
	os.system("find ./ | sed 's,^./,Print3DActivity.activity/,g' > MANIFEST")
	os.system('rm Print3DActivity.xo')
	os.chdir('..')
	os.system('zip -r Print3DActivity.xo Print3DActivity.activity')
	os.system('mv Print3DActivity.xo ./Print3DActivity.activity')
	os.chdir('Print3DActivity.activity')