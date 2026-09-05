export type TOCEntry = { title: string; href: string; children: TOCEntry[] };

export function parseAttributes(tagStr: string): Record<string, string> {
    const attrs: Record<string, string> = {};
    const regex = /(\w[\w-]*)="([^"]*)"/g;
    let m: RegExpExecArray | null;
    while ((m = regex.exec(tagStr)) !== null) {
        attrs[m[1]] = m[2];
    }
    return attrs;
}

export function htmlToPlainText(html: string): string {
    return html
        .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')
        .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '')
        .replace(/<br\s*\/?>/gi, '\n')
        .replace(/<\/p>/gi, '\n\n')
        .replace(/<\/div>/gi, '\n')
        .replace(/<\/h[1-6]>/gi, '\n\n')
        .replace(/<\/li>/gi, '\n')
        .replace(/<[^>]+>/g, '')
        .replace(/&nbsp;/g, ' ')
        .replace(/&amp;/g, '&')
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&quot;/g, '"')
        .replace(/&#39;/g, "'")
        .replace(/\n{3,}/g, '\n\n')
        .trim();
}

export function parseNCX(ncxContent: string): TOCEntry[] {
    const entries: TOCEntry[] = [];
    const navPointRegex = /<navPoint[^>]*>([\s\S]*?)<\/navPoint>/g;
    let match: RegExpExecArray | null;
    while ((match = navPointRegex.exec(ncxContent)) !== null) {
        const inner = match[1];
        const labelMatch = inner.match(/<text>\s*([\s\S]*?)\s*<\/text>/);
        const srcMatch = inner.match(/<content\s+src="([^"]+)"/);
        if (labelMatch && srcMatch) {
            entries.push({
                title: labelMatch[1].trim(),
                href: srcMatch[1].split('#')[0],
                children: [],
            });
        }
    }
    return entries;
}

export function parseNavToc(navContent: string): TOCEntry[] {
    const entries: TOCEntry[] = [];
    const linkRegex = /<a\s+[^>]*href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/g;
    let match: RegExpExecArray | null;
    while ((match = linkRegex.exec(navContent)) !== null) {
        entries.push({
            title: match[2].replace(/<[^>]+>/g, '').trim(),
            href: match[1].split('#')[0],
            children: [],
        });
    }
    return entries;
}

export function formatChaptersForClipboard(chapters: { title: string; text: string }[]): string {
    return chapters
        .map(ch => `=== ${ch.title} ===\n\n${ch.text}`)
        .join('\n\n---\n\n');
}

export function findCoverHrefInOpf(opfContent: string): string | null {
    const itemRegex = /<item\s+([^>]+?)\/?>/g;
    let match: RegExpExecArray | null;
    const items: { id: string; href: string; mediaType: string; properties?: string }[] = [];

    while ((match = itemRegex.exec(opfContent)) !== null) {
        const attrs = parseAttributes(match[1]);
        if (attrs.id && attrs.href) {
            items.push({
                id: attrs.id,
                href: attrs.href,
                mediaType: attrs['media-type'] || '',
                properties: attrs.properties || '',
            });
        }
    }

    const epub3Cover = items.find(i => 
        (i.properties && i.properties.includes('cover-image')) ||
        (i.mediaType.startsWith('image/') && i.id.toLowerCase() === 'cover-image')
    );
    if (epub3Cover) return epub3Cover.href;

    const metaMatch = opfContent.match(/<meta[^>]+name="cover"[^>]+content="([^"]+)"/i) ||
                      opfContent.match(/<meta[^>]+content="([^"]+)"[^>]+name="cover"/i);
    if (metaMatch) {
        const coverId = metaMatch[1];
        const metaCover = items.find(i => i.id === coverId);
        if (metaCover) return metaCover.href;
    }

    const patternCover = items.find(i => 
        i.mediaType.startsWith('image/') && (
            i.id.toLowerCase().includes('cover') ||
            i.href.toLowerCase().includes('cover') ||
            i.href.toLowerCase().includes('front')
        )
    );
    if (patternCover) return patternCover.href;

    const firstImage = items.find(i => i.mediaType.startsWith('image/'));
    return firstImage ? firstImage.href : null;
}

