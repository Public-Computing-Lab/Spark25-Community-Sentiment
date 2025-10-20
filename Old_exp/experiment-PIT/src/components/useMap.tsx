/**
 * useMap.tsx
 * This file hosts the react hook that child components can use to access MapProvider values
 * Used in Map.tsx and FilterDialog.tsx
 */


import { useContext } from 'react';
import { MapContext } from './MapContext';

export function useMap() {
    const context = useContext(MapContext);
    if (!context) {
        throw new Error('useMap must be used within a MapProvider');
    }
    return context;
}