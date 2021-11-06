#!/bin/bash

# minify all .css-files
ls -1 *.css|grep -Ev "min.css$" | while read cssfile; do
	newfile="${cssfile%.*}.min.css"
	echo "$cssfile --> $newfile"
	curl -X POST -s --data-urlencode "input@$cssfile" https://www.toptal.com/developers/cssminifier/raw > $newfile
done

# merge all into one single file
rm -f styles.min.css
cat *.min.css > styles.min.css
