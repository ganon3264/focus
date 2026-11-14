// Unit tests for assetUrl in media-utils.js — the client twin of
// focus/core/media.py::asset_url. Stored asset paths are filesystem paths;
// everything under ASSETS_DIR is served at /assets. The two implementations
// must agree, so the table below is mirrored in tests/units/test_media.py.

var h = require('./helpers.js');
var assertEqual = h.assertEqual;
var fs = require('fs');
var path = require('path');

global.window = global;
global.document = {
  createElement: function () {
    return h.makeElement('div');
  },
};
global.navigator = {};

eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'ui', 'media-utils.js'), 'utf8'));

var cases = [
  ['', ''],
  ['assets/characters/x/avatar.png', '/assets/characters/x/avatar.png'],
  ['/home/u/app/assets/characters/x/avatar.png', '/assets/characters/x/avatar.png'],
  ['characters/x/avatar.png', '/assets/characters/x/avatar.png'],
  ['tool/abc.png', '/assets/tool/abc.png'],
  ['/old/machine/assets/attachments/a.png', '/assets/attachments/a.png'],
  ['/assets/tool/a.png', '/assets/tool/a.png'],
  ['https://x/y.png', 'https://x/y.png'],
  ['data:image/png;base64,AA', 'data:image/png;base64,AA'],
  ['blob:http://x/1', 'blob:http://x/1'],
];

cases.forEach(function (pair) {
  assertEqual(window.assetUrl(pair[0]), pair[1], 'assetUrl(' + JSON.stringify(pair[0]) + ')');
});

h.printSummary();
