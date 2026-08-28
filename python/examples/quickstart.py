"""Minimal Linux/BlueZ example. Windows and macOS need another transport."""
from xkglasses import XkGlassesClient
mac='FA:00:11:12:F7:73'
c=XkGlassesClient(); c.connect(mac); c.bind(); c.setup()
count=c.photo_count(); print('photos:',count)
if count: print('saved:',c.download_photo(1,'photo.jpg'))
c.close()
