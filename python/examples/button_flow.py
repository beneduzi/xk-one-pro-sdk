"""Poll photo_num after starting the foreground session."""
from xkglasses import XkGlassesClient, build_7300
c=XkGlassesClient(); c.connect('FA:00:11:12:F7:73'); c.bind(); c.setup()
last=0
try:
    while True:
        n=c.photo_count()
        for i in range(last+1,n+1): c.download_photo(i,f'photo-{i}.jpg')
        last=n
finally: c.close()
# The physical button captures only while the app FGS session is active.
