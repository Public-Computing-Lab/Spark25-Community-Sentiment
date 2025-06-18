import React, { createContext, useContext, useRef } from 'react';

interface MapContextType {
    mapRef: React.RefObject<mapboxgl.Map | null>;
    mapContainerRef: React.RefObject<HTMLDivElement | null>;
}

//“teleporting” data to the components that need it without passing props
const MapContext = createContext<MapContextType | null>(null);

//MapProvider wraps its children components and provides them access to the mapRef and mapContainerRef via the context.
//children prop represents all the React components nested inside the MapProvider when it is used.
export const MapProvider = ({ children }: { children: React.ReactNode }) => {
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  return (
    <MapContext.Provider value={{mapRef, mapContainerRef}}>
        {children}
    </MapContext.Provider>
  );
};

export const useMap = () => {
    const context = useContext(MapContext);
    if (!context) {
        throw new Error('useMap must be used within a MapProvider');
    }
  return context;
}