// assets/app-script.js
let moveTimeout;


function initMaps() {
    mapboxgl.accessToken = window.MAPBOX_TOKEN;

    
    const beforeMap = new mapboxgl.Map({
      container: 'before-map',
      style:     'mapbox://styles/mapbox/light-v11',
      center:    [-71.07601, 42.28988],
      zoom:      13,
      interactive: true
    });
    window.beforeMap = beforeMap;

    
    const afterMap = new mapboxgl.Map({
      container: 'after-map',
      style:     'mapbox://styles/mapbox/streets-v12',
      center:    [-71.07601, 42.28988],
      zoom:      13,
      interactive: false
    });
    window.afterMap = afterMap;

    
    beforeMap.on('move', () => {
      afterMap.jumpTo({
        center:  beforeMap.getCenter(),
        zoom:    beforeMap.getZoom(),
        bearing: beforeMap.getBearing(),
        pitch:   beforeMap.getPitch()
      });
    });

    
    afterMap.on('load', () => {
      afterMap.addSource('hexData', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] }
      });
      afterMap.addLayer({
        id:     'hexLayer',
        type:   'fill',
        source: 'hexData',
        paint: {
          'fill-color': [
            'interpolate', ['linear'], ['get', 'value'],
            0, 'rgba(0,0,0,0)', 1, '#fdebcf', 5, '#f08e3e', 10, '#b13d14', 20, '#70250F'
          ],
          'fill-opacity':        0.6,
          'fill-outline-color':  'rgba(255,255,255,0.5)'
        }
      });
      afterMap.addSource('shotsData', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] }
      });
      afterMap.addLayer({
        id:     'shotsLayer',
        type:   'circle',
        source: 'shotsData',
        paint: {
          'circle-radius':  7,
          'circle-color':   '#A43800',
          'circle-opacity': 0.9
        }
      });
      afterMap.addSource('homicidesData', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] }
      });
      afterMap.addLayer({
        id:     'homicidesLayer',
        type:   'circle',
        source: 'homicidesData',
        paint: {
          'circle-radius':  7,
          'circle-color':   '#232E33',
          'circle-opacity': 0.9
        }
      });
    });

    
    beforeMap.on('moveend', () => {
      clearTimeout(moveTimeout);
      moveTimeout = setTimeout(() => {
        const center   = beforeMap.getCenter();
        const zoom     = beforeMap.getZoom();
        const features = afterMap.queryRenderedFeatures({ layers: ['hexLayer'] });
        const baseRad  = 0.015 * Math.pow(2, 13 - zoom);
        const hexIDs   = [];
        const eventIDs = [];

        features.forEach(f => {
          const p = f.properties;
          if (!p?.hex_id) return;
          const dLat = p.lat - center.lat,
                dLon = p.lon - center.lng;
          if (Math.sqrt(dLat*dLat + dLon*dLon) <= baseRad) {
            hexIDs.push(p.hex_id);
            if (p.ids) {
              let list = p.ids;
              if (typeof list === 'string') {
                try { list = JSON.parse(list); }
                catch(e) { console.warn("invalid p.ids JSON", list); list = []; }
              }
              eventIDs.push(...list);
            }
          }
        });

        console.log("🔍 JS saw hexes:", hexIDs, "events:", eventIDs);
        const mapBtn = document.getElementById('map-move-btn');
        if (!mapBtn) return console.error("map-move-btn not in DOM");
        mapBtn.setAttribute('data-hexids', hexIDs.join(','));
        mapBtn.setAttribute('data-ids',    eventIDs.join(','));
        mapBtn.click();

        
        setTimeout(() => {
          console.log("🔍 firing tell-me-btn");
          const refBtn = document.getElementById('refresh-chat-btn');
          if (refBtn) refBtn.click();
        }, 500);
      }, 3000);
    });
    
}


function waitForContainer() {
  if (document.getElementById('before-map') &&
      document.getElementById('after-map')) {
    initMaps();
  } else {
    setTimeout(waitForContainer, 100);
  }
}
document.addEventListener('DOMContentLoaded', waitForContainer);


window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.clientside = {
  updateMapData: function(hexData, shotsData, homData) {
    if (window.afterMap && window.afterMap.getSource) {
      let src = window.afterMap.getSource('hexData');
      if (src && hexData)    src.setData(hexData);
      src = window.afterMap.getSource('shotsData');
      if (src && shotsData)  src.setData(shotsData);
      src = window.afterMap.getSource('homicidesData');
      if (src && homData)    src.setData(homData);
    }
    return '';
  }
};


