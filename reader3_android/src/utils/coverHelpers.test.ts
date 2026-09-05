import { test, describe } from 'node:test';
import assert from 'node:assert';
import { findCoverHrefInOpf } from './textHelpers.ts';

describe('coverHelpers', () => {
    test('findCoverHrefInOpf detects EPUB3 properties="cover-image"', () => {
        const opf = `
        <manifest>
            <item id="ch1" href="text/ch1.xhtml" media-type="application/xhtml+xml"/>
            <item id="my-cover" href="images/cover_art.jpg" media-type="image/jpeg" properties="cover-image"/>
        </manifest>
        `;
        const href = findCoverHrefInOpf(opf);
        assert.strictEqual(href, 'images/cover_art.jpg');
    });

    test('findCoverHrefInOpf detects EPUB2 meta cover tag', () => {
        const opf = `
        <metadata>
            <meta name="cover" content="book-cover-id"/>
        </metadata>
        <manifest>
            <item id="book-cover-id" href="OEBPS/Images/cover.png" media-type="image/png"/>
            <item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>
        </manifest>
        `;
        const href = findCoverHrefInOpf(opf);
        assert.strictEqual(href, 'OEBPS/Images/cover.png');
    });

    test('findCoverHrefInOpf detects cover by href pattern', () => {
        const opf = `
        <manifest>
            <item id="img1" href="images/front_illustration.jpg" media-type="image/jpeg"/>
            <item id="img2" href="images/other.jpg" media-type="image/jpeg"/>
        </manifest>
        `;
        const href = findCoverHrefInOpf(opf);
        assert.strictEqual(href, 'images/front_illustration.jpg');
    });

    test('findCoverHrefInOpf falls back to first image when no cover tag exists', () => {
        const opf = `
        <manifest>
            <item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>
            <item id="diagram" href="assets/diagram.png" media-type="image/png"/>
        </manifest>
        `;
        const href = findCoverHrefInOpf(opf);
        assert.strictEqual(href, 'assets/diagram.png');
    });

    test('findCoverHrefInOpf returns null when no image exists in manifest', () => {
        const opf = `
        <manifest>
            <item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>
        </manifest>
        `;
        const href = findCoverHrefInOpf(opf);
        assert.strictEqual(href, null);
    });
});
