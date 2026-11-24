// Unit tests for api-paths.js — the builders that URL-encode their input
var h = require('./helpers.js');
var assertEqual = h.assertEqual;

global.window = global;
var path = require('path');
eval(require('fs').readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'core', 'api-paths.js'), 'utf8'));

assertEqual(api.providerSecret('my key'), '/api/providers/secrets/my%20key', 'providerSecret encodes');
assertEqual(api.providerOpenRouterCapabilities('vendor/model'), '/api/providers/openrouter/capabilities?model=vendor%2Fmodel', 'capabilities encode the model id');
assertEqual(api.extensionRun('a b'), '/api/extensions/a%20b/run', 'extensionRun encodes');

h.printSummary();
