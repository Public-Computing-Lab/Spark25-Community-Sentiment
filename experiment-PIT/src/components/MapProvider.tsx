
import React, { useRef, useState } from 'react';
import { MapContext } from '../components/MapContext';

export default function MapProvider({ children }: { children: React.ReactNode }) {
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  
  // Add state management
  const [selectedLayers, setSelectedLayer] = useState<string[]>(["Community Assets"]);
  const [selectedYearsSlider, setSelectedYearsSlider] = useState<number[]>([2018, 2024]);

  const [selectedData, setSelectedData] = useState<string[]>(["Community Assets"]);
  const [selectedYears, setSelectedYears] = useState<number[]>([2018, 2024]);
const [pendingFitBounds, setPendingFitBounds] = useState<[[number, number], [number, number]] | null>(null);
  //map provider works! it just takes time for the data to load...

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


