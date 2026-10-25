const { withDangerousMod } = require('expo/config-plugins');
const path = require('node:path');
const syncPdfjs = require('../scripts/sync-pdfjs.cjs');

module.exports = function withPdfjs(config) {
    return withDangerousMod(config, ['android', async (config) => {
        syncPdfjs(path.join(config.modRequest.platformProjectRoot, 'app', 'src', 'main', 'assets', 'pdfjs'));
        return config;
    }]);
};
