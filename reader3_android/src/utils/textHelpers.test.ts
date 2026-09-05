import { test, describe } from 'node:test';
import assert from 'node:assert';
import {
    htmlToPlainText,
    parseAttributes,
    parseNCX,
    parseNavToc,
    formatChaptersForClipboard,
} from './textHelpers.ts';

describe('textHelpers', () => {
    test('htmlToPlainText converts HTML markup to plain text', () => {
        const html = '<h1>Chapter 1</h1><p>Hello &amp; welcome to <b>Reader3</b>.&nbsp;Enjoy!</p>';
        const text = htmlToPlainText(html);
        assert.strictEqual(text, 'Chapter 1\n\nHello & welcome to Reader3. Enjoy!');
    });

    test('htmlToPlainText removes script and style tags', () => {
        const html = '<style>body{color:red;}</style><script>alert(1);</script><p>Content here</p>';
        const text = htmlToPlainText(html);
        assert.strictEqual(text, 'Content here');
    });

    test('parseAttributes extracts tag attributes correctly', () => {
        const tag = '<item id="chapter-1" href="text/ch1.xhtml" media-type="application/xhtml+xml"/>';
        const attrs = parseAttributes(tag);
        assert.strictEqual(attrs.id, 'chapter-1');
        assert.strictEqual(attrs.href, 'text/ch1.xhtml');
        assert.strictEqual(attrs['media-type'], 'application/xhtml+xml');
    });

    test('parseNCX extracts navigation points', () => {
        const ncx = `
        <navMap>
            <navPoint id="navPoint-1" playOrder="1">
                <navLabel><text>Introduction</text></navLabel>
                <content src="Text/intro.xhtml#start"/>
            </navPoint>
            <navPoint id="navPoint-2" playOrder="2">
                <navLabel><text>Chapter One</text></navLabel>
                <content src="Text/ch1.xhtml"/>
            </navPoint>
        </navMap>
        `;
        const toc = parseNCX(ncx);
        assert.strictEqual(toc.length, 2);
        assert.strictEqual(toc[0].title, 'Introduction');
        assert.strictEqual(toc[0].href, 'Text/intro.xhtml');
        assert.strictEqual(toc[1].title, 'Chapter One');
        assert.strictEqual(toc[1].href, 'Text/ch1.xhtml');
    });

    test('parseNavToc extracts links from EPUB3 nav', () => {
        const nav = `
        <nav epub:type="toc">
            <ol>
                <li><a href="ch1.xhtml#title">Chapter 1</a></li>
                <li><a href="ch2.xhtml">Chapter 2</a></li>
            </ol>
        </nav>
        `;
        const toc = parseNavToc(nav);
        assert.strictEqual(toc.length, 2);
        assert.strictEqual(toc[0].title, 'Chapter 1');
        assert.strictEqual(toc[0].href, 'ch1.xhtml');
        assert.strictEqual(toc[1].title, 'Chapter 2');
        assert.strictEqual(toc[1].href, 'ch2.xhtml');
    });

    test('formatChaptersForClipboard formats multi-chapter clipboard content', () => {
        const chapters = [
            { title: 'Chapter 1', text: 'This is the first chapter.' },
            { title: 'Chapter 2', text: 'This is the second chapter.' },
        ];
        const formatted = formatChaptersForClipboard(chapters);
        const expected = '=== Chapter 1 ===\n\nThis is the first chapter.\n\n---\n\n=== Chapter 2 ===\n\nThis is the second chapter.';
        assert.strictEqual(formatted, expected);
    });
});
