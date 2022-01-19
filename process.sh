cd web
find . -type f -name "._*" -delete
find . -name "*.jpeg" -exec sh -c 'mv "$1" "${1%.jpeg}.jpg"' _ {} \;
cd ../scanner
./main.py ../web/albums ../web/cache
