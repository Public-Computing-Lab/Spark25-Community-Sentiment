import { createContext } from 'react';
import mapboxgl from 'mapbox-gl';

interface MapContextType {
    mapRef: React.RefObject<mapboxgl.Map | null>;
    mapContainerRef: React.RefObject<HTMLDivElement | null>;
    selectedLayers: string[];
    setSelectedLayer: React.Dispatch<React.SetStateAction<string[]>>;
    selectedYears: number[];
    setSelectedYears: React.Dispatch<React.SetStateAction<number[]>>;
    selectedData: string[];
    setSelectedData: React.Dispatch<React.SetStateAction<string[]>>;
    selectedYearsSlider: number[];
    setSelectedYearsSlider: React.Dispatch<React.SetStateAction<number[]>>;
    pendingFitBounds: [[number, number], [number, number]] | null;
    setPendingFitBounds: React.Dispatch<React.SetStateAction<[[number, number], [number, number]] | null>>;
}

export const MapContext = createContext<MapContextType | null>(null);