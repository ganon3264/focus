// Unit tests for api_paths.js — all route builders
var failures = 0, tests = 0;

function assert(cond, msg) { tests++; if (!cond) { console.error('FAIL: ' + msg); failures++; } else console.log('OK:   ' + msg); }
function assertEqual(a, b, msg) { tests++; if (a !== b) { console.error('FAIL: ' + msg + ' — expected ' + JSON.stringify(b) + ', got ' + JSON.stringify(a)); failures++; } else console.log('OK:   ' + msg); }

global.window = global;
var path = require('path');
eval(require('fs').readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'core', 'api_paths.js'), 'utf8'));

// ── String constants ──
assertEqual(api.chats, '/api/chats', 'api.chats');
assertEqual(api.charImport, '/api/characters/import', 'api.charImport');
assertEqual(api.charTrash, '/api/characters/trash', 'api.charTrash');
assertEqual(api.presets, '/api/presets', 'api.presets');
assertEqual(api.providers, '/api/providers', 'api.providers');
assertEqual(api.stream, '/api/stream', 'api.stream');
assertEqual(api.itemize, '/api/itemize', 'api.itemize');
assertEqual(api.export, '/api/export', 'api.export');
assertEqual(api.import_, '/api/import', 'api.import_');
assertEqual(api.cleanDb, '/api/db/clean', 'api.cleanDb');
assertEqual(api.backups, '/api/backups', 'api.backups');

// ── Chat routes ──
assertEqual(api.chat('c1'), '/api/chats/c1', 'api.chat');
assertEqual(api.chatAttachments('c1'), '/api/chats/c1/attachments', 'api.chatAttachments');
assertEqual(api.chatMessages('c1'), '/api/chats/c1/messages', 'api.chatMessages');
assertEqual(api.chatMessage('c1', 'm1'), '/api/chats/c1/messages/m1', 'api.chatMessage');
assertEqual(api.chatBulkDelete('c1'), '/api/chats/c1/messages/bulk_delete', 'api.chatBulkDelete');
assertEqual(api.chatSwipe('c1', 'm1'), '/api/chats/c1/messages/m1/swipe', 'api.chatSwipe');
assertEqual(api.chatBranch('c1', 'm1'), '/api/chats/c1/messages/m1/branch', 'api.chatBranch');

// ── Character routes ──
assertEqual(api.characters('ch1'), '/api/characters/ch1', 'api.characters');
assertEqual(api.charRestore('ch1', true), '/api/characters/ch1/restore?restore_chats=true', 'api.charRestore with true');
assertEqual(api.charRestore('ch1', false), '/api/characters/ch1/restore?restore_chats=false', 'api.charRestore with false');
assertEqual(api.charHardDelete('ch1'), '/api/characters/ch1?hard=true', 'api.charHardDelete');
assertEqual(api.charDelete('ch1', true), '/api/characters/ch1?delete_chats=true', 'api.charDelete with true');
assertEqual(api.charDelete('ch1', false), '/api/characters/ch1?delete_chats=false', 'api.charDelete with false');
assertEqual(api.charImages('ch1'), '/api/characters/ch1/images', 'api.charImages');
assertEqual(api.charImage('ch1', 'img1'), '/api/characters/ch1/images/img1', 'api.charImage');
assertEqual(api.charAvatar('ch1'), '/api/characters/ch1/avatar', 'api.charAvatar');
assertEqual(api.charBlocks('ch1'), '/api/characters/ch1/blocks', 'api.charBlocks');
assertEqual(api.charBlock('ch1', 'b1'), '/api/characters/ch1/blocks/b1', 'api.charBlock');
assertEqual(api.charBlockImages('ch1', 'b1'), '/api/characters/ch1/blocks/b1/images', 'api.charBlockImages');
assertEqual(api.charBlockImage('ch1', 'b1', 'i1'), '/api/characters/ch1/blocks/b1/images/i1', 'api.charBlockImage');

// ── Persona routes ──
assertEqual(api.personas('p1'), '/api/personas/p1', 'api.personas');
assertEqual(api.personaImages('p1'), '/api/personas/p1/images', 'api.personaImages');
assertEqual(api.personaImage('p1', 'img1'), '/api/personas/p1/images/img1', 'api.personaImage');
assertEqual(api.personaAvatar('p1'), '/api/personas/p1/avatar', 'api.personaAvatar');

// ── Preset routes ──
assertEqual(api.preset('pr1'), '/api/presets/pr1', 'api.preset');
assertEqual(api.presetBlocks('pr1'), '/api/presets/pr1/blocks', 'api.presetBlocks');
assertEqual(api.presetBlock('pr1', 'b1'), '/api/presets/pr1/blocks/b1', 'api.presetBlock');
assertEqual(api.presetBlockImages('pr1', 'b1'), '/api/presets/pr1/blocks/b1/images', 'api.presetBlockImages');
assertEqual(api.presetBlockImage('pr1', 'b1', 'i1'), '/api/presets/pr1/blocks/b1/images/i1', 'api.presetBlockImage');

// ── Provider routes ──
assertEqual(api.provider('prv1'), '/api/providers/prv1', 'api.provider');
assertEqual(api.providerOREndpoint('model1'), '/api/providers/openrouter/endpoints/model1', 'api.providerOREndpoint');
assertEqual(api.providerSecret('sk-test'), '/api/providers/secrets/sk-test', 'api.providerSecret');
assertEqual(api.providerSecret('my key'), '/api/providers/secrets/my%20key', 'api.providerSecret encodes');

// ── Backup routes ──
assertEqual(api.backupRestore('b1'), '/api/backups/b1/restore', 'api.backupRestore');
assertEqual(api.backupDelete('b1'), '/api/backups/b1', 'api.backupDelete');

// ── Partials ──
assertEqual(api.partials.messageList('c1'), '/partials/message-list/c1', 'partials.messageList');
assertEqual(api.partials.promptArranger('pr1'), '/partials/prompt-arranger/pr1', 'partials.promptArranger');
assertEqual(api.partials.presetEditor('pr1'), '/partials/preset-editor/pr1', 'partials.presetEditor');
assertEqual(api.partials.presetVariables('pr1'), '/partials/preset-variables/pr1', 'partials.presetVariables');

// ── Special characters in IDs ──
assertEqual(api.chat('abc-123'), '/api/chats/abc-123', 'chat with hyphen');
assertEqual(api.characters('abc_123'), '/api/characters/abc_123', 'characters with underscore');

// ── Result ──
console.log('\n' + tests + ' tests, ' + failures + ' failures');
process.exit(failures > 0 ? 1 : 0);
