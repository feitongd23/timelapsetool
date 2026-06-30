// Copyright (c) 2026 杜非同. All rights reserved.
// Part of Timelapse Tool — proprietary software.
// Unauthorized copying, modification, or distribution is prohibited.

const { thumbUrl, nextFrameIndex } = require("../electron/renderer/preview.js");

test("thumbUrl 拼接编码后的查询", () => {
  const url = thumbUrl("http://h", "/a b/raw", "0001.ARW");
  expect(url).toBe("http://h/preview/thumb?folder=%2Fa%20b%2Fraw&name=0001.ARW");
});

test("nextFrameIndex 循环递增", () => {
  expect(nextFrameIndex(0, 3)).toBe(1);
  expect(nextFrameIndex(2, 3)).toBe(0);
  expect(nextFrameIndex(0, 0)).toBe(0);
});
