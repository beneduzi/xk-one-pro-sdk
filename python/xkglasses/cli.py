import argparse
from .client import XkGlassesClient
def main():
    p=argparse.ArgumentParser(); p.add_argument('--mac',required=True); p.add_argument('action',choices=('connect','count','photo','watch')); p.add_argument('--out',default='photo.jpg'); a=p.parse_args(); c=XkGlassesClient(); c.connect(a.mac); c.bind(); c.setup()
    if a.action=='count': print(c.photo_count())
    elif a.action=='photo': print(c.download_photo(1,a.out) and a.out)
    elif a.action=='watch': print('watching')
    c.close()
