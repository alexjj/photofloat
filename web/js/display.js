/*
 * The page: album view, photo view, keyboard/mouse-wheel navigation and
 * metadata display. Uses the PhotoFloat class (photofloat.js) for loading
 * albums and working out image URLs.
 */
(function() {
	"use strict";

	/* Globals */

	var currentAlbum = null;
	var currentPhoto = null;
	var currentPhotoIndex = -1;
	var previousAlbum = null;
	var previousPhoto = null;
	var originalTitle = document.title;
	var photoFloat = new PhotoFloat();
	var THUMB_SIZE = 150; /* CSS pixels, matches the stylesheet */
	var shownPhotoSize = 0; /* size of the photo file currently displayed */
	var lastWheel = 0;

	/* Small DOM helpers */

	function $(selector) {
		return document.querySelector(selector);
	}
	function $$(selector) {
		return Array.prototype.slice.call(document.querySelectorAll(selector));
	}
	/* Like jQuery, quietly ignore elements that aren't on the page */
	function show(element, display) {
		if (element)
			element.style.display = display || "block";
	}
	function hide(element) {
		if (element)
			element.style.display = "none";
	}
	function isVisible(element) {
		return getComputedStyle(element).display !== "none";
	}
	function escapeHtml(text) {
		return String(text).replace(/[&<>"']/g, function(c) {
			return { "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[c];
		});
	}
	function fade(element, to, duration) {
		var from = isVisible(element) ? parseFloat(getComputedStyle(element).opacity) : 0;
		if (to > 0)
			show(element);
		element.style.opacity = to;
		if (from === to) {
			if (to === 0)
				hide(element);
			return;
		}
		var animation = element.animate([{ opacity: from }, { opacity: to }], { duration: duration, easing: "ease" });
		if (to === 0) {
			animation.onfinish = function() {
				if (element.style.opacity === "0")
					hide(element);
			};
		}
	}
	function smoothScroll() {
		return window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";
	}


	/* Displays */

	function setTitle() {
		var title = "", documentTitle = "", last = "", components, i;
		if (!currentAlbum.path.length)
			components = [originalTitle];
		else {
			components = currentAlbum.path.split("/");
			components.unshift(originalTitle);
		}
		if (currentPhoto !== null)
			documentTitle += photoFloat.trimExtension(currentPhoto.name);
		for (i = 0; i < components.length; ++i) {
			if (i || currentPhoto !== null)
				documentTitle += " « ";
			if (i)
				last += "/" + components[i];
			if (i < components.length - 1 || currentPhoto !== null)
				title += "<a href=\"#!/" + escapeHtml(i ? photoFloat.cachePath(last.substring(1)) : "") + "\">";
			title += escapeHtml(components[i]);
			documentTitle += components[components.length - 1 - i];
			if (i < components.length - 1 || currentPhoto !== null) {
				title += "</a>";
				title += " &raquo; ";
			}
		}
		if (currentPhoto !== null)
			title += escapeHtml(photoFloat.trimExtension(currentPhoto.name));
		$("#title").innerHTML = title;
		document.title = documentTitle;
	}

	function scrollToThumb() {
		var photo = currentPhoto, thumb = null, scroller, rect, scrollerRect;
		if (photo === null) {
			photo = previousPhoto;
			if (photo === null)
				return;
		}
		$$("#thumbs img").some(function(image) {
			if (image.photo === photo) {
				thumb = image;
				return true;
			}
			return false;
		});
		if (thumb === null)
			return;
		rect = thumb.getBoundingClientRect();
		if (currentPhoto !== null) {
			scroller = $("#album-view");
			scrollerRect = scroller.getBoundingClientRect();
			scroller.scrollTo({
				left: rect.left - scrollerRect.left + scroller.scrollLeft - scroller.clientWidth / 2 + rect.width / 2,
				behavior: smoothScroll()
			});
			$$("#thumbs img").forEach(function(image) { image.classList.remove("current-thumb"); });
			thumb.classList.add("current-thumb");
		} else {
			window.scrollTo({
				top: rect.top + window.pageYOffset - window.innerHeight / 2 + rect.height,
				behavior: smoothScroll()
			});
		}
	}

	function thumbSources(album, photo) {
		var sizes = photoFloat.options.thumbSizes, srcset = [], i;
		for (i = 0; i < sizes.length; ++i)
			srcset.push(photoFloat.photoPath(album, photo, sizes[i], true) + " " + (sizes[i] / THUMB_SIZE) + "x");
		return {
			src: photoFloat.photoPath(album, photo, photoFloat.pickSize(sizes, THUMB_SIZE), true),
			srcset: srcset.join(", "),
			best: photoFloat.photoPath(album, photo, photoFloat.thumbSize(THUMB_SIZE), true)
		};
	}

	function showAlbum(populate) {
		var i, thumbsElement, subalbumsElement;
		if (currentPhoto === null && previousPhoto === null)
			window.scrollTo({ top: 0, behavior: smoothScroll() });

		if (populate) {
			thumbsElement = $("#thumbs");
			subalbumsElement = $("#subalbums");
			thumbsElement.textContent = "";
			subalbumsElement.textContent = "";

			currentAlbum.photos.slice().forEach(function(photo) {
				var link = document.createElement("a");
				var image = document.createElement("img");
				var name = photoFloat.trimExtension(photo.name);
				var sources = thumbSources(currentAlbum, photo);
				var album = currentAlbum;
				link.href = "#!/" + photoFloat.photoHash(currentAlbum, photo);
				image.title = name;
				image.alt = name;
				image.width = THUMB_SIZE;
				image.height = THUMB_SIZE;
				image.loading = "lazy";
				image.decoding = "async";
				if (photo.mediaType === "video") {
					image.style.backgroundImage = "url(\"" + sources.best + "\")";
					image.src = "img/video-icon.png";
				} else {
					image.srcset = sources.srcset;
					image.src = sources.src;
				}
				image.photo = photo;
				image.addEventListener("error", function() {
					var index = album.photos.indexOf(photo);
					link.remove();
					if (index !== -1)
						album.photos.splice(index, 1);
				});
				link.appendChild(image);
				thumbsElement.appendChild(link);
			});

			for (i = currentAlbum.albums.length - 1; i >= 0; --i) {
				(function(theContainer, theAlbum) {
					var link = document.createElement("a");
					var button = document.createElement("div");
					link.href = "#!/" + photoFloat.albumHash(theAlbum);
					button.title = theAlbum.date;
					button.className = "album-button";
					button.textContent = theAlbum.path;
					link.appendChild(button);
					subalbumsElement.appendChild(link);
					photoFloat.albumPhoto(theAlbum, function(album, photo) {
						button.style.backgroundImage = "url(\"" + photoFloat.photoPath(album, photo, photoFloat.thumbSize(THUMB_SIZE), true) + "\")";
					}, function() {
						var index = theContainer.albums.indexOf(theAlbum);
						if (index !== -1)
							theContainer.albums.splice(index, 1);
						link.remove();
					});
				})(currentAlbum, currentAlbum.albums[i]);
			}

			if (currentAlbum.albums.length > 1)
				thumbsElement.parentNode.insertBefore(subalbumsElement, thumbsElement);
			else
				thumbsElement.parentNode.insertBefore(thumbsElement, subalbumsElement);
		}

		if (currentPhoto === null) {
			$$("#thumbs img").forEach(function(image) { image.classList.remove("current-thumb"); });
			$("#album-view").classList.remove("photo-view-container");
			show($("#subalbums"));
			hide($("#photo-view"));
			$("#video-box-inner").textContent = "";
			hide($("#video-box"));
		}
		setTimeout(scrollToThumb, 1);
	}

	function getDecimal(fraction) {
		if (!Array.isArray(fraction))
			return String(fraction);
		if (Math.abs(fraction[0]) < Math.abs(fraction[1]) && fraction[0] !== 0)
			return fraction[0] + "/" + fraction[1];
		return String(Math.round(fraction[0] / fraction[1] * 100) / 100);
	}

	/* Size (CSS pixels) the photo container gives to a photo of this ratio. */
	function displaySize(ratio) {
		var container = $("#photo-view"), width, height;
		if (document.fullscreenElement || document.webkitFullscreenElement) {
			width = screen.width;
			height = screen.height;
		} else {
			width = container.clientWidth;
			height = container.clientHeight;
		}
		if (height * ratio > width)
			return { width: width, height: width / ratio };
		return { width: height * ratio, height: height };
	}

	/* Which generated size of `photo` to show, so it's sharp on this screen. */
	function photoSizeFor(photo) {
		var ratio = photo.size[0] / photo.size[1];
		var display = displaySize(ratio);
		var pixels = Math.max(display.width, display.height) * (window.devicePixelRatio || 1);
		return photoFloat.photoSize(pixels);
	}

	function scaleImage() {
		var image = $("#photo"), container = $("#photo-view");
		if (container.clientHeight * parseFloat(image.getAttribute("ratio")) > container.clientWidth) {
			image.style.width = "100%";
			image.style.height = "auto";
			image.style.position = "absolute";
			image.style.bottom = "0";
		} else {
			image.style.height = "100%";
			image.style.width = "auto";
			image.style.position = "";
			image.style.bottom = "";
		}
	}

	function scaleVideo() {
		var video = $("#video"), container = $("#photo-view"), parent, ratio, width, height;
		if (video === null)
			return;
		parent = video.parentNode;
		ratio = parseFloat(video.getAttribute("ratio"));
		width = parseFloat(video.getAttribute("width"));
		height = parseFloat(video.getAttribute("height"));
		if (width > container.clientWidth && container.clientHeight * ratio > container.clientWidth) {
			video.style.width = container.clientWidth + "px";
			video.style.height = container.clientWidth / ratio + "px";
			parent.style.height = container.clientWidth / ratio + "px";
			parent.style.marginTop = -container.clientWidth / ratio / 2 + "px";
			parent.style.top = "50%";
		} else if (height > container.clientHeight && container.clientHeight * ratio < container.clientWidth) {
			video.style.height = container.clientHeight + "px";
			video.style.width = container.clientHeight * ratio + "px";
			parent.style.height = "100%";
			parent.style.marginTop = "0";
			parent.style.top = "0";
		} else {
			video.style.height = "";
			video.style.width = "";
			parent.style.height = height + "px";
			parent.style.marginTop = -height / 2 + "px";
			parent.style.top = "50%";
		}
	}

	function preloadImages() {
		for (var i = 0; i < arguments.length; ++i)
			(new Image()).src = arguments[i];
	}

	function updateImageLink(href) {
		$$("link[rel=image_src]").forEach(function(link) { link.remove(); });
		var link = document.createElement("link");
		link.rel = "image_src";
		link.href = href;
		document.head.appendChild(link);
	}

	/* Load a bigger version of the photo if the window grew (or went fullscreen). */
	function upgradePhoto() {
		if (currentPhoto === null || currentPhoto.mediaType === "video")
			return;
		var size = photoSizeFor(currentPhoto);
		if (size > shownPhotoSize) {
			shownPhotoSize = size;
			$("#photo").src = photoFloat.photoPath(currentAlbum, currentPhoto, size, false);
		}
	}

	function showPhoto() {
		var width, height, photoSrc, videoSrc, video, image, previous, next, nextLink, text, size, ratio;
		width = currentPhoto.size[0];
		height = currentPhoto.size[1];
		ratio = width / height;

		/* Show the photo view first: its size decides which image file to load */
		$("#album-view").classList.add("photo-view-container");
		hide($("#subalbums"));
		show($("#photo-view"));

		if (currentPhoto.mediaType === "video") {
			$("#video-box-inner").textContent = "";
			video = document.createElement("video");
			if (!video.canPlayType || !video.canPlayType("video/mp4; codecs=\"avc1.42E01E, mp4a.40.2\"")) {
				$("#video-box-inner").innerHTML = "<div id=\"video-unsupported\"><p>Sorry, your browser doesn't support the H.264 video format!</p></div>";
			} else {
				videoSrc = photoFloat.videoPath(currentAlbum, currentPhoto);
				video.id = "video";
				video.controls = true;
				video.preload = "metadata";
				video.setAttribute("width", width);
				video.setAttribute("height", height);
				video.setAttribute("ratio", ratio);
				video.setAttribute("playsinline", "");
				video.addEventListener("loadstart", scaleVideo);
				video.src = videoSrc;
				$("#video-box-inner").appendChild(video);
			}
			$("#video-box-inner").style.height = height + "px";
			$("#video-box-inner").style.marginTop = -height / 2 + "px";
			hide($("#photo-box"));
			show($("#video-box"), "inline");
		} else {
			size = photoSizeFor(currentPhoto);
			shownPhotoSize = size;
			if (width > height) {
				height = Math.round(height / width * Math.min(size, width));
				width = Math.min(size, width);
			} else {
				width = Math.round(width / height * Math.min(size, height));
				height = Math.min(size, height);
			}
			photoSrc = photoFloat.photoPath(currentAlbum, currentPhoto, size, false);
			image = $("#photo");
			image.setAttribute("width", width);
			image.setAttribute("height", height);
			image.setAttribute("ratio", ratio);
			image.alt = currentPhoto.name;
			image.title = currentPhoto.date;
			image.src = photoSrc;
			scaleImage();
			updateImageLink(photoSrc);
			$("#video-box-inner").textContent = "";
			hide($("#video-box"));
			show($("#photo-box"), "inline");
		}

		previous = currentAlbum.photos[
			(currentPhotoIndex - 1 < 0) ? (currentAlbum.photos.length - 1) : (currentPhotoIndex - 1)
		];
		next = currentAlbum.photos[
			(currentPhotoIndex + 1 >= currentAlbum.photos.length) ? 0 : (currentPhotoIndex + 1)
		];
		[next, previous].forEach(function(photo) {
			if (photo.mediaType !== "video")
				preloadImages(photoFloat.photoPath(currentAlbum, photo, photoSizeFor(photo), false));
		});

		nextLink = "#!/" + photoFloat.photoHash(currentAlbum, next);
		$("#next-photo").href = nextLink;
		$("#next").href = nextLink;
		$("#back").href = "#!/" + photoFloat.photoHash(currentAlbum, previous);
		$("#original-link").href = photoFloat.originalPhotoPath(currentAlbum, currentPhoto);

		function row(label, value) {
			text += "<tr><td>" + label + "</td><td>" + escapeHtml(value) + "</td></tr>";
		}
		text = "<table>";
		if (typeof currentPhoto.make !== "undefined") row("Camera Maker", currentPhoto.make);
		if (typeof currentPhoto.model !== "undefined") row("Camera Model", currentPhoto.model);
		if (typeof currentPhoto.lens !== "undefined") row("Lens", currentPhoto.lens);
		if (typeof currentPhoto.date !== "undefined") row("Time Taken", currentPhoto.date);
		if (typeof currentPhoto.size !== "undefined") row("Resolution", currentPhoto.size[0] + " x " + currentPhoto.size[1]);
		if (typeof currentPhoto.aperture !== "undefined") row("Aperture", "f/" + getDecimal(currentPhoto.aperture));
		if (typeof currentPhoto.focalLength !== "undefined") row("Focal Length", getDecimal(currentPhoto.focalLength) + " mm");
		if (typeof currentPhoto.subjectDistanceRange !== "undefined") row("Subject Distance Range", currentPhoto.subjectDistanceRange);
		if (typeof currentPhoto.iso !== "undefined") row("ISO", currentPhoto.iso);
		if (typeof currentPhoto.sceneCaptureType !== "undefined") row("Scene Capture Type", currentPhoto.sceneCaptureType);
		if (typeof currentPhoto.exposureTime !== "undefined") row("Exposure Time", getDecimal(currentPhoto.exposureTime) + " sec");
		if (typeof currentPhoto.exposureProgram !== "undefined") row("Exposure Program", currentPhoto.exposureProgram);
		if (typeof currentPhoto.exposureCompensation !== "undefined") row("Exposure Compensation", getDecimal(currentPhoto.exposureCompensation));
		if (typeof currentPhoto.spectralSensitivity !== "undefined") row("Spectral Sensitivity", currentPhoto.spectralSensitivity);
		if (typeof currentPhoto.sensingMethod !== "undefined") row("Sensing Method", currentPhoto.sensingMethod);
		if (typeof currentPhoto.lightSource !== "undefined") row("Light Source", currentPhoto.lightSource);
		if (typeof currentPhoto.flash !== "undefined") row("Flash", currentPhoto.flash);
		if (typeof currentPhoto.orientation !== "undefined") row("Orientation", currentPhoto.orientation);
		text += "</table>";
		$("#metadata").innerHTML = text;
	}


	/* Error displays */

	function die(error) {
		if (error == 403) {
			fade($("#auth-text"), 1, 1000);
			$("#password").focus();
		} else
			fade($("#error-text"), 1, 2500);
		fade($("#error-overlay"), 0.8, 500);
		document.documentElement.style.overflow = "hidden";
		document.body.style.overflow = "hidden";
	}
	function undie() {
		["#error-text", "#error-overlay", "#auth-text"].forEach(function(selector) {
			fade($(selector), 0, 500);
		});
		document.documentElement.style.overflow = "";
		document.body.style.overflow = "";
	}


	/* Entry point for most events */

	function hashParsed(album, photo, photoIndex) {
		undie();
		hide($("#loading"));
		if (album === currentAlbum && photo === currentPhoto)
			return;
		previousAlbum = currentAlbum;
		previousPhoto = currentPhoto;
		currentAlbum = album;
		currentPhoto = photo;
		currentPhotoIndex = photoIndex;
		setTitle();
		if (photo !== null)
			showPhoto();
		showAlbum(previousAlbum !== currentAlbum);
	}

	function hashChanged() {
		show($("#loading"));
		photoFloat.parseHash(location.hash, hashParsed, die);
	}

	function go(selector) {
		var href = $(selector).getAttribute("href");
		if (href)
			window.location.href = href;
	}


	/* Event listeners */

	function start() {
		var title = photoFloat.options.title;
		if (title) {
			originalTitle = title;
			document.title = title;
			$("#title").textContent = title;
		}
		if (photoFloat.options.downloadOriginals === false) {
			hide($("#original-link"));
			hide($("#original-divider"));
		}

		window.addEventListener("hashchange", hashChanged);
		hashChanged();

		document.addEventListener("keydown", function(e) {
			if (currentPhoto === null || e.altKey || e.ctrlKey || e.metaKey)
				return;
			if (e.target && /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName))
				return;
			if (e.key === "ArrowRight") {
				go("#next");
				e.preventDefault();
			} else if (e.key === "ArrowLeft") {
				go("#back");
				e.preventDefault();
			} else if (e.key === "Escape" && !document.fullscreenElement) {
				window.location.href = "#!/" + photoFloat.albumHash(currentAlbum);
			}
		});

		document.addEventListener("wheel", function(e) {
			var now;
			if (currentPhoto === null || e.ctrlKey)
				return;
			/* Let the thumbnail strip scroll sideways */
			if (Math.abs(e.deltaX) > Math.abs(e.deltaY))
				return;
			e.preventDefault();
			/* Trackpads send many events per swipe: move one photo at a time */
			now = Date.now();
			if (now - lastWheel < 350 || e.deltaY === 0)
				return;
			lastWheel = now;
			go(e.deltaY > 0 ? "#next" : "#back");
		}, { passive: false });

		window.addEventListener("resize", function() {
			if (currentPhoto === null)
				return;
			if (currentPhoto.mediaType === "video")
				scaleVideo();
			else {
				scaleImage();
				upgradePhoto();
			}
		});

		var photo = $("#photo");
		var requestFullscreen = photo.requestFullscreen || photo.webkitRequestFullscreen;
		if (requestFullscreen && (document.fullscreenEnabled || document.webkitFullscreenEnabled)) {
			show($("#fullscreen-divider"), "inline");
			show($("#fullscreen"), "inline");
			$("#fullscreen").addEventListener("click", function() {
				requestFullscreen.call(photo);
			});
			["fullscreenchange", "webkitfullscreenchange"].forEach(function(name) {
				document.addEventListener(name, upgradePhoto);
			});
		}

		$("#metadata-link").addEventListener("click", function() {
			var metadata = $("#metadata"), link = this, height;
			metadata.getAnimations().forEach(function(animation) { animation.cancel(); });
			if (link.textContent.indexOf("show") !== -1) {
				show(metadata);
				height = metadata.scrollHeight;
				metadata.animate([
					{ height: "0px", paddingTop: "0px", paddingBottom: "0px" },
					{ height: height + "px", paddingTop: "3px", paddingBottom: "3px" }
				], { duration: 600, easing: "ease" });
				link.textContent = link.textContent.replace("show", "hide");
			} else {
				height = metadata.offsetHeight;
				metadata.animate([
					{ height: height + "px", paddingTop: "3px", paddingBottom: "3px" },
					{ height: "0px", paddingTop: "0px", paddingBottom: "0px" }
				], { duration: 600, easing: "ease" }).onfinish = function() {
					hide(metadata);
				};
				link.textContent = link.textContent.replace("hide", "show");
			}
		});

		$("#auth-form").addEventListener("submit", function(e) {
			var password = $("#password");
			e.preventDefault();
			password.style.backgroundColor = "rgb(128, 128, 200)";
			photoFloat.authenticate(password.value, function(success) {
				password.value = "";
				if (success) {
					password.style.backgroundColor = "rgb(200, 200, 200)";
					photoFloat.albumCache = {};
					hashChanged();
				} else
					password.style.backgroundColor = "rgb(255, 64, 64)";
			});
		});
	}

	photoFloat.loadOptions().then(start);
}());
