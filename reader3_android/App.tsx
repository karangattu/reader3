import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import LibraryScreen from './src/screens/LibraryScreen';
import PDFReaderScreen from './src/screens/PDFReaderScreen';
import EpubReaderScreen from './src/screens/EpubReaderScreen';

const Stack = createNativeStackNavigator();

export default function App() {
    return (
        <SafeAreaProvider>
            <NavigationContainer>
                <Stack.Navigator
                    initialRouteName="Library"
                    screenOptions={{
                        headerShown: false,
                    }}
                >
                    <Stack.Screen name="Library" component={LibraryScreen} />
                    <Stack.Screen name="PDFReader" component={PDFReaderScreen} />
                    <Stack.Screen name="EpubReader" component={EpubReaderScreen} />
                </Stack.Navigator>
            </NavigationContainer>
        </SafeAreaProvider>
    );
}
