/*
 * PhotoFloat: fetches the album JSON files made by the scanner and works
 * out the URLs of the generated images. The file naming must match
 * photofloat/cachepath.py.
 */
(function() {
	"use strict";

	function PhotoFloat() {
		this.albumCache = {};
		this.options = {
			title: null,
			thumbSizes: [150, 300],
			photoSizes: [1024, 1600],
			downloadOriginals: true
		};
	}

	function getJSON(url) {
		return fetch(url, { credentials: "same-origin" }).then(function(response) {
			if (!response.ok) {
				var error = new Error("HTTP " + response.status);
				error.status = response.status;
				throw error;
			}
			return response.json();
		});
	}

	/* Scanner settings (image sizes, title). Missing on old caches: keep defaults. */
	PhotoFloat.prototype.loadOptions = function() {
		var self = this;
		return getJSON("cache/options.json").then(function(options) {
			for (var key in options)
				self.options[key] = options[key];
			self.options.thumbSizes.sort(function(a, b) { return a - b; });
			self.options.photoSizes.sort(function(a, b) { return a - b; });
		}, function() {});
	};

	PhotoFloat.prototype.album = function(subalbum, callback, error) {
		var cacheKey, self = this;
		if (typeof subalbum.photos !== "undefined" && subalbum.photos !== null) {
			callback(subalbum);
			return;
		}
		if (typeof subalbum === "string")
			cacheKey = subalbum;
		else
			cacheKey = PhotoFloat.cachePath(subalbum.parent.path + "/" + subalbum.path);
		if (Object.prototype.hasOwnProperty.call(this.albumCache, cacheKey)) {
			callback(this.albumCache[cacheKey]);
			return;
		}
		getJSON("cache/" + cacheKey + ".json").then(function(album) {
			var i;
			for (i = 0; i < album.albums.length; ++i)
				album.albums[i].parent = album;
			for (i = 0; i < album.photos.length; ++i)
				album.photos[i].parent = album;
			self.albumCache[cacheKey] = album;
			callback(album);
		}, function(e) {
			if (typeof error === "function")
				error(e.status || 0);
		});
	};

	/* Picks a random photo somewhere inside an album, for album covers. */
	PhotoFloat.prototype.albumPhoto = function(subalbum, callback, error) {
		var self = this;
		function nextAlbum(album) {
			var index = Math.floor(Math.random() * (album.photos.length + album.albums.length));
			if (index >= album.photos.length) {
				index -= album.photos.length;
				self.album(album.albums[index], nextAlbum, error);
			} else
				callback(album, album.photos[index]);
		}
		if (typeof subalbum.photos !== "undefined" && subalbum.photos !== null)
			nextAlbum(subalbum);
		else
			this.album(subalbum, nextAlbum, error);
	};

	PhotoFloat.prototype.parseHash = function(hash, callback, error) {
		var index, album, photo;
		hash = PhotoFloat.cleanHash(hash);
		index = hash.lastIndexOf("/");
		if (!hash.length) {
			album = PhotoFloat.cachePath("root");
			photo = null;
		} else if (index !== -1 && index !== hash.length - 1) {
			photo = hash.substring(index + 1);
			album = hash.substring(0, index);
		} else {
			album = hash;
			photo = null;
		}
		this.album(album, function(theAlbum) {
			var i = -1;
			if (photo !== null) {
				for (i = 0; i < theAlbum.photos.length; ++i) {
					if (PhotoFloat.cachePath(theAlbum.photos[i].name) === photo) {
						photo = theAlbum.photos[i];
						break;
					}
				}
				if (i >= theAlbum.photos.length) {
					photo = null;
					i = -1;
				}
			}
			callback(theAlbum, photo, i);
		}, error);
	};

	PhotoFloat.prototype.authenticate = function(password, result) {
		fetch("auth?username=photos&password=" + encodeURIComponent(password), { credentials: "same-origin" })
			.then(function(response) { result(response.ok); }, function() { result(false); });
	};

	/* Smallest generated thumbnail that is sharp at `cssSize` px on this screen. */
	PhotoFloat.prototype.thumbSize = function(cssSize) {
		return this.pickSize(this.options.thumbSizes, cssSize * (window.devicePixelRatio || 1));
	};

	/* Smallest generated photo size whose longest side covers `pixels`. */
	PhotoFloat.prototype.photoSize = function(pixels) {
		return this.pickSize(this.options.photoSizes, pixels);
	};

	PhotoFloat.prototype.pickSize = function(sizes, pixels) {
		for (var i = 0; i < sizes.length; ++i) {
			if (sizes[i] >= pixels)
				return sizes[i];
		}
		return sizes[sizes.length - 1];
	};

	/* static functions */
	PhotoFloat.cachePath = function(path) {
		if (path === "")
			return "root";
		if (path.charAt(0) === "/")
			path = path.substring(1);
		path = path
			.replace(/ /g, "_")
			.replace(/\//g, "-")
			.replace(/[()#&,\[\]"']/g, "")
			.replace(/_-_/g, "-")
			.toLowerCase();
		while (path.indexOf("--") !== -1)
			path = path.replace(/--/g, "-");
		while (path.indexOf("__") !== -1)
			path = path.replace(/__/g, "_");
		return path;
	};
	PhotoFloat.photoHash = function(album, photo) {
		return PhotoFloat.albumHash(album) + "/" + PhotoFloat.cachePath(photo.name);
	};
	PhotoFloat.albumHash = function(album) {
		if (typeof album.photos !== "undefined" && album.photos !== null)
			return PhotoFloat.cachePath(album.path);
		return PhotoFloat.cachePath(album.parent.path + "/" + album.path);
	};
	/* Photos in the root album are cached as "root-<name>", others as "<album>-<name>". */
	PhotoFloat.photoPath = function(album, photo, size, square) {
		var suffix = size.toString() + (square ? "s" : "");
		return "cache/" + PhotoFloat.cachePath(PhotoFloat.photoHash(album, photo) + "_" + suffix + ".jpg");
	};
	PhotoFloat.videoPath = function(album, video) {
		return "cache/" + PhotoFloat.cachePath(PhotoFloat.photoHash(album, video) + ".mp4");
	};
	PhotoFloat.originalPhotoPath = function(album, photo) {
		var path = album.path ? album.path + "/" + photo.name : photo.name;
		return "albums/" + path.split("/").map(encodeURIComponent).join("/");
	};
	PhotoFloat.trimExtension = function(name) {
		var index = name.lastIndexOf(".");
		if (index !== -1)
			return name.substring(0, index);
		return name;
	};
	PhotoFloat.cleanHash = function(hash) {
		while (hash.length) {
			if (hash.charAt(0) === "#")
				hash = hash.substring(1);
			else if (hash.charAt(0) === "!")
				hash = hash.substring(1);
			else if (hash.charAt(0) === "/")
				hash = hash.substring(1);
			else if (hash.substring(0, 3) === "%21")
				hash = hash.substring(3);
			else if (hash.charAt(hash.length - 1) === "/")
				hash = hash.substring(0, hash.length - 1);
			else
				break;
		}
		try {
			hash = decodeURIComponent(hash);
		} catch (e) {}
		return hash;
	};

	/* make static methods callable as member functions */
	["cachePath", "photoHash", "albumHash", "photoPath", "videoPath", "originalPhotoPath", "trimExtension", "cleanHash"]
		.forEach(function(name) { PhotoFloat.prototype[name] = PhotoFloat[name]; });

	window.PhotoFloat = PhotoFloat;
}());
