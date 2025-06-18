import { useContext } from 'react';
import { MapContext } from './MapContext';

export function useMap() {
    const context = useContext(MapContext);
    if (!context) {
        throw new Error('useMap must be used within a MapProvider');
    }
    return context;
}
