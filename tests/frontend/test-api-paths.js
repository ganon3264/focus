// Unit tests for api-paths.js — all route builders
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual;

global.window = global;
var path = require('path');
eval(require('fs').readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'core', 'api-paths.js'), 'utf8'));

// ── String constants ──
assertEqual(api.chats, '/api/chats', 'api.chats');
assertEqual(api.charImport, '/api/characters/import', 'api.charImport');
assertEqual(api.providers, '/api/providers', 'api.providers');
assertEqual(api.stream, '/api/stream', 'api.stream');
assertEqual(api.export, '/api/export', 'api.export');
assertEqual(api.import_, '/api/import', 'api.import_');
assertEqual(api.cleanDb, '/api/db/clean', 'api.cleanDb');
assertEqual(api.backups, '/api/backups', 'api.backups');

// ── Chat routes ──
assertEqual(api.chatAttachments('c1'), '/api/chats/c1/attachments', 'api.chatAttachments');
assertEqual(api.chatMessage('c1', 'm1'), '/api/chats/c1/messages/m1', 'api.chatMessage');
assertEqual(api.chatBulkDelete('c1'), '/api/chats/c1/messages/bulk_delete', 'api.chatBulkDelete');
assertEqual(api.chatBranch('c1', 'm1'), '/api/chats/c1/messages/m1/branch', 'api.chatBranch');

// ── Character routes ──
assertEqual(api.characters('ch1'), '/api/characters/ch1', 'api.characters');
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

// ── Provider routes ──
assertEqual(api.provider('prv1'), '/api/providers/prv1', 'api.provider');
assertEqual(api.providerActiveKey('prv1'), '/api/providers/prv1/active-key', 'api.providerActiveKey');
assertEqual(api.providerSecret('sk-test'), '/api/providers/secrets/sk-test', 'api.providerSecret');
assertEqual(api.providerSecret('my key'), '/api/providers/secrets/my%20key', 'api.providerSecret encodes');

// ── Backup routes ──
assertEqual(api.backupRestore('b1'), '/api/backups/b1/restore', 'api.backupRestore');
assertEqual(api.backupDelete('b1'), '/api/backups/b1', 'api.backupDelete');

// ── Partials ──
assertEqual(api.partials.messageList('c1'), '/partials/message-list/c1', 'partials.messageList');

// ── Special characters in IDs ──
assertEqual(api.chatAttachments('abc-123'), '/api/chats/abc-123/attachments', 'chat with hyphen');
assertEqual(api.characters('abc_123'), '/api/characters/abc_123', 'characters with underscore');

// ── Result ──
h.printSummary();
