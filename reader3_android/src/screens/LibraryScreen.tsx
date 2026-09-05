import React, { useState, useCallback, useRef } from 'react';
import {
    View, Text, StyleSheet, FlatList, TouchableOpacity, RefreshControl,
    Alert, Image,
} from 'react-native';
import { WebView, WebViewMessageEvent } from 'react-native-webview';
import * as DocumentPicker from 'expo-document-picker';
import { Paths, Directory, File } from 'expo-file-system';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useNavigation, useFocusEffect } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import FontAwesome from '@expo/vector-icons/FontAwesome';
import { extractEpubCover } from '../utils/coverHelpers.ts';

const BOOKS_STORAGE_KEY = '@reader3:books';

export type BookEntry = {
    id: string;
    title: string;
    filename: string;
    uri: string;
    type: 'pdf' | 'epub';
    addedAt: number;
    coverUri?: string;
};

const PDF_COVER_EXTRACTOR_HTML = `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<script src="file:///android_asset/pdfjs/pdf.min.js"></script>
<script>
if (typeof pdfjsLib === 'undefined') {
    document.write('<script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"><\\/script>');
}
</script>
</head>
<body>
<script>
if (window.pdfjsLib) {
    pdfjsLib.GlobalWorkerOptions.workerSrc = 'file:///android_asset/pdfjs/pdf.worker.min.js';
}

function loadPdfArrayBuffer(uri) {
    return new Promise(function(resolve, reject) {
        var xhr = new XMLHttpRequest();
        xhr.open('GET', uri, true);
        xhr.responseType = 'arraybuffer';
        xhr.onload = function() {
            if (xhr.status === 200 || xhr.status === 0) {
                if (xhr.response && xhr.response.byteLength > 0) {
                    resolve(new Uint8Array(xhr.response));
                } else {
                    reject(new Error('Empty file'));
                }
            } else {
                reject(new Error('Status: ' + xhr.status));
            }
        };
        xhr.onerror = function() {
            reject(new Error('XHR error'));
        };
        xhr.send();
    });
}

window.extractCover = async function(id, fileUri) {
    try {
        if (!window.pdfjsLib) throw new Error('PDF.js not loaded');
        var uint8 = await loadPdfArrayBuffer(fileUri);
        var doc = await pdfjsLib.getDocument({ data: uint8 }).promise;
        var page = await doc.getPage(1);
        var baseViewport = page.getViewport({ scale: 1 });
        var scale = 240 / baseViewport.width;
        var viewport = page.getViewport({ scale: Math.max(scale, 0.4) });
        var canvas = document.createElement('canvas');
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        var ctx = canvas.getContext('2d');
        await page.render({ canvasContext: ctx, viewport: viewport }).promise;
        var dataUrl = canvas.toDataURL('image/jpeg', 0.85);
        window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'pdfCover', id: id, dataUrl: dataUrl }));
    } catch(e) {
        window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'pdfCoverError', id: id, message: e.message }));
    }
};
</script>
</body>
</html>`;

export default function LibraryScreen() {
    const [books, setBooks] = useState<BookEntry[]>([]);
    const [refreshing, setRefreshing] = useState(false);
    const navigation = useNavigation<any>();
    const insets = useSafeAreaInsets();
    const pdfWebviewRef = useRef<WebView>(null);

    const triggerPdfCoverExtraction = useCallback((id: string, uri: string) => {
        pdfWebviewRef.current?.injectJavaScript(`
            if (window.extractCover) {
                window.extractCover(${JSON.stringify(id)}, ${JSON.stringify(uri)});
            }
            true;
        `);
    }, []);

    const loadBooks = useCallback(async () => {
        try {
            setRefreshing(true);
            const storedBooks = await AsyncStorage.getItem(BOOKS_STORAGE_KEY);
            if (storedBooks) {
                const parsed: BookEntry[] = JSON.parse(storedBooks);
                setBooks(parsed);

                // Background cover extraction for any books missing covers
                for (const b of parsed) {
                    if (!b.coverUri) {
                        if (b.type === 'epub') {
                            extractEpubCover(b.uri, b.id).then(cUri => {
                                if (cUri) {
                                    setBooks(prev => {
                                        const updated = prev.map(book => book.id === b.id ? { ...book, coverUri: cUri } : book);
                                        AsyncStorage.setItem(BOOKS_STORAGE_KEY, JSON.stringify(updated));
                                        return updated;
                                    });
                                }
                            }).catch(() => {});
                        } else if (b.type === 'pdf') {
                            triggerPdfCoverExtraction(b.id, b.uri);
                        }
                    }
                }
            }
        } catch { } finally {
            setRefreshing(false);
        }
    }, [triggerPdfCoverExtraction]);

    useFocusEffect(
        useCallback(() => {
            loadBooks();
        }, [loadBooks])
    );

    const saveBooks = async (newBooks: BookEntry[]) => {
        try {
            await AsyncStorage.setItem(BOOKS_STORAGE_KEY, JSON.stringify(newBooks));
            setBooks(newBooks);
        } catch { }
    };

    const onPdfCoverMessage = (event: WebViewMessageEvent) => {
        try {
            const data = JSON.parse(event.nativeEvent.data);
            if (data.type === 'pdfCover' && data.id && data.dataUrl) {
                const base64 = data.dataUrl.replace(/^data:image\/[a-z]+;base64,/, '');
                const coversDir = new Directory(Paths.document, 'covers');
                if (!coversDir.exists) coversDir.create();
                const coverFile = new File(coversDir, `${data.id}_cover.jpg`);
                coverFile.write(base64, { encoding: 'base64' });

                setBooks(prev => {
                    const updated = prev.map(b => b.id === data.id ? { ...b, coverUri: coverFile.uri } : b);
                    AsyncStorage.setItem(BOOKS_STORAGE_KEY, JSON.stringify(updated));
                    return updated;
                });
            }
        } catch { }
    };

    const handleImport = async () => {
        try {
            const result = await DocumentPicker.getDocumentAsync({
                type: '*/*',
                copyToCacheDirectory: true,
            });

            if (!result.canceled && result.assets && result.assets.length > 0) {
                const file = result.assets[0];

                const booksDir = new Directory(Paths.document, 'books');
                if (!booksDir.exists) {
                    booksDir.create();
                }

                const ext = file.name.split('.').pop()?.toLowerCase();
                let type: 'pdf' | 'epub' = 'pdf';
                if (ext === 'epub' || file.mimeType === 'application/epub+zip') {
                    type = 'epub';
                }

                const id = Date.now().toString();
                const newFilename = `${id}_${file.name}`;
                const newFile = new File(booksDir, newFilename);

                const sourceFile = new File(file.uri);
                sourceFile.copy(newFile);

                let coverUri: string | undefined = undefined;
                if (type === 'epub') {
                    try {
                        const extracted = await extractEpubCover(newFile.uri, id);
                        if (extracted) coverUri = extracted;
                    } catch { }
                }

                const newBook: BookEntry = {
                    id,
                    title: file.name.replace(/\.[^/.]+$/, ''),
                    filename: newFilename,
                    uri: newFile.uri,
                    type,
                    addedAt: Date.now(),
                    coverUri,
                };

                const updated = [newBook, ...books];
                await saveBooks(updated);

                if (type === 'pdf') {
                    triggerPdfCoverExtraction(id, newFile.uri);
                }
            }
        } catch (err: any) {
            Alert.alert('Import Failed', err.message || 'Failed to import document.');
        }
    };

    const handleOpenBook = (book: BookEntry) => {
        if (book.type === 'pdf') {
            navigation.navigate('PDFReader', { book });
        } else if (book.type === 'epub') {
            navigation.navigate('EpubReader', { book });
        }
    };

    const handleDeleteBook = async (bookId: string) => {
        const bookToDelete = books.find(b => b.id === bookId);
        if (!bookToDelete) return;

        try {
            const file = new File(bookToDelete.uri);
            if (file.exists) {
                file.delete();
            }
            if (bookToDelete.coverUri) {
                const coverFile = new File(bookToDelete.coverUri);
                if (coverFile.exists) coverFile.delete();
            }

            const updatedBooks = books.filter(b => b.id !== bookId);
            await saveBooks(updatedBooks);
        } catch { }
    };

    const renderItem = ({ item }: { item: BookEntry }) => (
        <View style={styles.bookCard}>
            <TouchableOpacity
                style={styles.bookInfo}
                onPress={() => handleOpenBook(item)}
            >
                {item.coverUri ? (
                    <Image
                        source={{ uri: item.coverUri }}
                        style={styles.bookCover}
                        resizeMode="cover"
                    />
                ) : (
                    <View style={[
                        styles.bookCoverPlaceholder,
                        item.type === 'epub' ? styles.epubCoverPlaceholder : styles.pdfCoverPlaceholder,
                    ]}>
                        <View style={styles.spineEffect} />
                        <View style={styles.coverBadge}>
                            <Text style={styles.coverBadgeText}>{item.type.toUpperCase()}</Text>
                        </View>
                        <Text style={styles.coverPlaceholderTitle} numberOfLines={3}>{item.title}</Text>
                    </View>
                )}

                <View style={styles.textContainer}>
                    <Text style={styles.bookTitle} numberOfLines={2}>{item.title}</Text>
                    <View style={styles.formatPill}>
                        <Text style={styles.formatPillText}>{item.type.toUpperCase()}</Text>
                    </View>
                    <Text style={styles.bookDate}>
                        Added: {new Date(item.addedAt).toLocaleDateString()}
                    </Text>
                </View>
            </TouchableOpacity>

            <TouchableOpacity
                style={styles.deleteButton}
                onPress={() => handleDeleteBook(item.id)}
            >
                <View style={styles.btnRow}>
                    <FontAwesome name="trash-o" size={15} color="#ff3b30" />
                    <Text style={styles.deleteText}>Delete</Text>
                </View>
            </TouchableOpacity>
        </View>
    );

    return (
        <View style={[styles.safeArea, { paddingTop: insets.top }]}>
            <View style={styles.container}>
                <View style={styles.header}>
                    <Text style={styles.headerTitle}>Reader3 Library</Text>
                    <TouchableOpacity style={styles.importButton} onPress={handleImport}>
                        <View style={styles.btnRow}>
                            <FontAwesome name="plus" size={13} color="#fff" />
                            <Text style={styles.importButtonText}>Import</Text>
                        </View>
                    </TouchableOpacity>
                </View>

                {books.length === 0 ? (
                    <View style={styles.emptyContainer}>
                        <FontAwesome name="book" size={56} color="#c7c7cc" style={{ marginBottom: 16 }} />
                        <Text style={styles.emptyText}>Your library is empty.</Text>
                        <Text style={styles.emptySubText}>Tap Import to add EPUB or PDF files.</Text>
                    </View>
                ) : (
                    <FlatList
                        data={books}
                        keyExtractor={(item) => item.id}
                        renderItem={renderItem}
                        contentContainerStyle={[
                            styles.listContainer,
                            { paddingBottom: Math.max(insets.bottom + 20, 30) },
                        ]}
                        refreshControl={
                            <RefreshControl refreshing={refreshing} onRefresh={loadBooks} />
                        }
                    />
                )}
            </View>

            <WebView
                ref={pdfWebviewRef}
                originWhitelist={['*']}
                source={{ html: PDF_COVER_EXTRACTOR_HTML, baseUrl: 'file:///' }}
                style={styles.hiddenWebview}
                javaScriptEnabled={true}
                allowFileAccess={true}
                allowFileAccessFromFileURLs={true}
                allowUniversalAccessFromFileURLs={true}
                onMessage={onPdfCoverMessage}
            />
        </View>
    );
}

const styles = StyleSheet.create({
    safeArea: {
        flex: 1,
        backgroundColor: '#f5f5f7',
    },
    container: {
        flex: 1,
        backgroundColor: '#f5f5f7',
    },
    header: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        paddingHorizontal: 20,
        paddingVertical: 15,
        backgroundColor: '#ffffff',
        borderBottomWidth: 1,
        borderBottomColor: '#e0e0e0',
    },
    headerTitle: {
        fontSize: 24,
        fontWeight: 'bold',
        color: '#333333',
    },
    importButton: {
        backgroundColor: '#007AFF',
        paddingHorizontal: 16,
        paddingVertical: 8,
        borderRadius: 20,
    },
    importButtonText: {
        color: '#ffffff',
        fontWeight: 'bold',
    },
    btnRow: {
        flexDirection: 'row',
        alignItems: 'center',
        gap: 5,
    },
    listContainer: {
        padding: 15,
    },
    bookCard: {
        flexDirection: 'row',
        backgroundColor: '#ffffff',
        borderRadius: 12,
        marginBottom: 15,
        padding: 12,
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.1,
        shadowRadius: 4,
        elevation: 2,
        alignItems: 'center',
        justifyContent: 'space-between',
    },
    bookInfo: {
        flexDirection: 'row',
        alignItems: 'center',
        flex: 1,
    },
    bookCover: {
        width: 65,
        height: 92,
        borderRadius: 6,
        marginRight: 14,
        backgroundColor: '#e1e1e8',
    },
    bookCoverPlaceholder: {
        width: 65,
        height: 92,
        borderRadius: 6,
        marginRight: 14,
        padding: 6,
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        overflow: 'hidden',
        position: 'relative',
    },
    spineEffect: {
        position: 'absolute',
        left: 0,
        top: 0,
        bottom: 0,
        width: 5,
        backgroundColor: 'rgba(0,0,0,0.25)',
    },
    epubCoverPlaceholder: {
        backgroundColor: '#2c3e50',
    },
    pdfCoverPlaceholder: {
        backgroundColor: '#a33327',
    },
    coverBadge: {
        backgroundColor: 'rgba(255,255,255,0.25)',
        paddingHorizontal: 5,
        paddingVertical: 2,
        borderRadius: 3,
        marginLeft: 3,
    },
    coverBadgeText: {
        color: '#ffffff',
        fontSize: 9,
        fontWeight: 'bold',
    },
    coverPlaceholderTitle: {
        color: '#ffffff',
        fontSize: 9,
        fontWeight: '600',
        lineHeight: 12,
        marginLeft: 3,
    },
    textContainer: {
        flex: 1,
        justifyContent: 'center',
    },
    bookTitle: {
        fontSize: 16,
        fontWeight: '600',
        color: '#333333',
        marginBottom: 4,
    },
    formatPill: {
        alignSelf: 'flex-start',
        backgroundColor: '#eef2f7',
        paddingHorizontal: 6,
        paddingVertical: 2,
        borderRadius: 4,
        marginBottom: 4,
    },
    formatPillText: {
        fontSize: 10,
        color: '#555',
        fontWeight: '600',
    },
    bookDate: {
        fontSize: 12,
        color: '#8e8e93',
    },
    deleteButton: {
        padding: 10,
    },
    deleteText: {
        color: '#FF3B30',
        fontWeight: '500',
    },
    emptyContainer: {
        flex: 1,
        justifyContent: 'center',
        alignItems: 'center',
        padding: 40,
    },
    emptyText: {
        fontSize: 18,
        fontWeight: '600',
        color: '#333333',
        marginBottom: 8,
    },
    emptySubText: {
        fontSize: 14,
        color: '#8e8e93',
        textAlign: 'center',
    },
    hiddenWebview: {
        width: 0,
        height: 0,
        position: 'absolute',
        opacity: 0,
    },
});
