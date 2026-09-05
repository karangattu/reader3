import JSZip from 'jszip';
import { Paths, Directory, File } from 'expo-file-system';
import { findCoverHrefInOpf } from './textHelpers.ts';

export async function extractEpubCover(epubUri: string, bookId: string): Promise<string | null> {
    try {
        const file = new File(epubUri);
        const data = await file.arrayBuffer();
        const zip = await JSZip.loadAsync(data);

        const containerXml = await zip.file('META-INF/container.xml')?.async('text');
        if (!containerXml) return null;

        const rootfileMatch = containerXml.match(/rootfile[^>]+full-path="([^"]+)"/);
        if (!rootfileMatch) return null;

        const opfPath = rootfileMatch[1];
        const opfDir = opfPath.includes('/') ? opfPath.substring(0, opfPath.lastIndexOf('/') + 1) : '';
        const opfContent = await zip.file(opfPath)?.async('text');
        if (!opfContent) return null;

        const coverHref = findCoverHrefInOpf(opfContent);
        if (!coverHref) return null;

        const coverRelPath = opfDir + decodeURIComponent(coverHref);
        const base64 = await zip.file(coverRelPath)?.async('base64');
        if (!base64) return null;

        const coversDir = new Directory(Paths.document, 'covers');
        if (!coversDir.exists) coversDir.create();

        const ext = coverHref.split('.').pop()?.toLowerCase() || 'jpg';
        const coverFile = new File(coversDir, `${bookId}_cover.${ext}`);
        coverFile.write(base64, { encoding: 'base64' });
        return coverFile.uri;
    } catch {
        return null;
    }
}
