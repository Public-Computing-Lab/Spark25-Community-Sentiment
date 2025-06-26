/**
 * MapProvider.tsx
 * This file hosts the data structures used in the Map component to make it accessible to any components necessary
 * Used by Map.tsx and FilterDialog.tsx through useMap.tsx
 */

import React, { useRef, useState } from 'react';
import { MapContext } from '../components/MapContext';

export default function MapProvider({ children }: { children: React.ReactNode }) {
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  
  //filters in Map.tsx
  const [selectedLayers, setSelectedLayer] = useState<string[]>(["Community Assets"]); 
  const [selectedYearsSlider, setSelectedYearsSlider] = useState<number[]>([2018, 2024]);

  //filters in FilterDialog.tsx 
  const [selectedData, setSelectedData] = useState<string[]>(["Community Assets"]); 
  const [selectedYears, setSelectedYears] = useState<number[]>([2018, 2024]);

  //zoom boundaries used in map-chat link
  const [pendingFitBounds, setPendingFitBounds] = useState<[[number, number], [number, number]] | null>(null);

  return (
    <MapContext.Provider value={{
        mapRef,
        mapContainerRef,
        selectedLayers,
        setSelectedLayer,
        selectedYears,
        setSelectedYears,
        selectedData,
        setSelectedData,
        selectedYearsSlider,
        setSelectedYearsSlider,
        pendingFitBounds,
        setPendingFitBounds,
        }}>
        {children}
    </MapContext.Provider> 
  );
}