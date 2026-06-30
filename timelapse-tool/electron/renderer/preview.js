// Copyright (c) 2026 杜非同. All rights reserved.
// Part of Timelapse Tool — proprietary software.
// Unauthorized copying, modification, or distribution is prohibited.

function thumbUrl(httpBase, folder, name) {
  return httpBase + "/preview/thumb?folder=" + encodeURIComponent(folder) + "&name=" + name;
}

function nextFrameIndex(i, len) {
  if (!len) return 0;
  return (i + 1) % len;
}

if (typeof window !== "undefined") {
  window.preview = { thumbUrl, nextFrameIndex };
}
if (typeof module !== "undefined") {
  module.exports = { thumbUrl, nextFrameIndex };
}
