// 
// Map Controls and Rendering
// 
let moveTimeout;


function initMaps() {
  mapboxgl.accessToken = window.MAPBOX_TOKEN;


  const beforeMap = new mapboxgl.Map({
    container: 'before-map',
    style: 'mapbox://styles/mapbox/light-v11',
    center: [-71.07601, 42.28988],
    zoom: 13,
    interactive: true,
  });
  window.beforeMap = beforeMap;


  const afterMap = new mapboxgl.Map({
    container: 'after-map',
    style: 'mapbox://styles/mapbox/streets-v12',
    center: [-71.07601, 42.28988],
    zoom: 13,
    interactive: false
  });
  window.afterMap = afterMap;


  beforeMap.on('move', () => {
    afterMap.jumpTo({
      center: beforeMap.getCenter(),
      zoom: beforeMap.getZoom(),
      bearing: beforeMap.getBearing(),
      pitch: beforeMap.getPitch()
    });
  });


  afterMap.on('load', () => {
    afterMap.addSource('hexData', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] }
    });
    afterMap.addLayer({
      id: 'hexLayer',
      type: 'fill',
      source: 'hexData',
      paint: {
        'fill-color': [
          'interpolate', ['linear'],
          ['get', 'value'],
          0, 'rgba(0,0,0,0)', 1, '#fdebcf', 5, '#f08e3e', 10, '#b13d14', 20, '#70250F'
        ],
        'fill-opacity': 0.6,
        'fill-outline-color': 'rgba(255,255,255,0.5)'
      }
    });
    afterMap.addSource('shotsData', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] }
    });
    afterMap.addLayer({
      id: 'shotsLayer',
      type: 'circle',
      source: 'shotsData',
      paint: {
        'circle-radius': 7,
        'circle-color': '#A43800',
        'circle-opacity': 0.9
      }
    });
    afterMap.addSource('homicidesData', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] }
    });
    afterMap.addLayer({
      id: 'homicidesLayer',
      type: 'circle',
      source: 'homicidesData',
      paint: {
        'circle-radius': 7,
        'circle-color': '#232E33',
        'circle-opacity': 0.9
      }
    });
  });


  beforeMap.on('moveend', () => {
    clearTimeout(moveTimeout);
    moveTimeout = setTimeout(() => {
      const center = beforeMap.getCenter();
      const zoom = beforeMap.getZoom();
      const features = afterMap.queryRenderedFeatures({ layers: ['hexLayer'] });
      const baseRad = 0.015 * Math.pow(2, 13 - zoom);
      const hexIDs = [];
      const eventIDs = [];

      features.forEach(f => {
        const p = f.properties;
        if (!p?.hex_id) return;
        const dLat = p.lat - center.lat,
          dLon = p.lon - center.lng;
        if (Math.sqrt(dLat * dLat + dLon * dLon) <= baseRad) {
          hexIDs.push(p.hex_id);
          if (p.ids) {
            let list = p.ids;
            if (typeof list === 'string') {
              try { list = JSON.parse(list); } catch (e) {
                console.warn("invalid p.ids JSON", list);
                list = [];
              }
            }
            eventIDs.push(...list);
          }
        }
      });

      console.log("🔍 JS saw hexes:", hexIDs, "events:", eventIDs);
      const mapBtn = document.getElementById('map-move-btn');
      if (!mapBtn) return console.error("map-move-btn not in DOM");
      mapBtn.setAttribute('data-hexids', hexIDs.join(','));
      mapBtn.setAttribute('data-ids', eventIDs.join(','));
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


window.dash_clientside = window.dash_clientside || {};
window.dash_clientside.clientside = {
  updateMapData: function(hexData, shotsData, homData) {
    if (window.afterMap && window.afterMap.getSource) {
      let src = window.afterMap.getSource('hexData');
      if (src && hexData) src.setData(hexData);
      src = window.afterMap.getSource('shotsData');
      if (src && shotsData) src.setData(shotsData);
      src = window.afterMap.getSource('homicidesData');
      if (src && homData) src.setData(homData);
    }
    return '';
  }
};

// 
// Circular Slider Controls
// 

function initCircularSlider() {


  // Constants for the slider
  const center = { x: 300, y: 300 };
  const radius = 270;
  const startAngle = 135; // Degrees (bottom-left of circle)
  const endAngle = 225; // Degrees (bottom-right of circle)
  const totalAngle = endAngle - startAngle;

  // Date range: Jan 2018 to Dec 2024 (84 months total)
  const startDate = new Date(2018, 0); // January 2018
  const endDate = new Date(2024, 11); // December 2024
  const totalMonths = 84;

  // Elements
  const svgElement = document.getElementById('slider-svg');
  const handleElement = document.getElementById('handle');
  const activeArcElement = document.getElementById('active-arc');
  const startLabelElement = document.getElementById('start-label');
  const endLabelElement = document.getElementById('end-label');
  const currentDateElement = document.querySelector('.current-date');

  // State
  let currentAngle = startAngle;
  let isDragging = false;
  let currentDate = new Date(startDate);

  // Initialize
  initializeSlider();

  function initializeSlider() {
    // Draw the active arc
    activeArcElement.setAttribute('d', createArc(center.x, center.y, radius, startAngle, endAngle));

    // Position the start and end labels
    const startPos = polarToCartesian(center.x, center.y, radius + 30, startAngle);
    startLabelElement.setAttribute('x', startPos.x);
    startLabelElement.setAttribute('y', startPos.y);

    const endPos = polarToCartesian(center.x, center.y, radius + 30, endAngle);
    endLabelElement.setAttribute('x', endPos.x);
    endLabelElement.setAttribute('y', endPos.y);

    // Create tick marks and year labels
    createTickMarksAndLabels();

    // Set initial handle position
    updateHandlePosition(currentAngle);

    // Set up event listeners
    svgElement.addEventListener('mousedown', handleStart);
    svgElement.addEventListener('touchstart', handleStart, { passive: false });
  }

  // Create tick marks for each month and labels for January of each year
  function createTickMarksAndLabels() {
    const tickMarksGroup = document.getElementById('tick-marks');
    const yearLabelsGroup = document.getElementById('year-labels');

    // For each month in the range
    for (let year = 2018; year <= 2024; year++) {
      for (let month = 0; month < 12; month++) {
        // Skip months outside our range
        if (year === 2024 && month > 11) continue;

        const date = new Date(year, month);
        const angle = dateToAngle(date);

        // Create tick mark
        const innerPos = polarToCartesian(center.x, center.y, radius - 10, angle);
        const outerPos = polarToCartesian(center.x, center.y, radius + 10, angle);

        const tickLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        tickLine.setAttribute('x1', innerPos.x);
        tickLine.setAttribute('y1', innerPos.y);
        tickLine.setAttribute('x2', outerPos.x);
        tickLine.setAttribute('y2', outerPos.y);

        // January gets a thicker tick mark
        if (month === 0) {
          tickLine.setAttribute('class', 'tick-mark-january');

          // Add year label for January
          const labelPos = polarToCartesian(center.x, center.y, radius + 25, angle);

          const yearLabel = document.createElementNS('http://www.w3.org/2000/svg', 'text');
          yearLabel.setAttribute('x', labelPos.x);
          yearLabel.setAttribute('y', labelPos.y);
          yearLabel.setAttribute('class', 'year-label');
          yearLabel.textContent = year;

          yearLabelsGroup.appendChild(yearLabel);
        } else {
          tickLine.setAttribute('class', 'tick-mark');
        }

        tickMarksGroup.appendChild(tickLine);
      }
    }
  }

  // Convert angle to date (reversed direction)
  function angleToDate(angle) {
    // Normalize angle to the range [0, totalAngle]
    const normalizedAngle = angle - startAngle;

    // Convert to month index (0 to totalMonths-1) with reversed mapping
    // Higher angle should give earlier date
    const monthIndex = Math.round(((totalAngle - normalizedAngle) / totalAngle) * (totalMonths - 1));

    // Create new date object
    const newDate = new Date(startDate);
    newDate.setMonth(startDate.getMonth() + monthIndex);

    return newDate;
  }

  // Convert date to angle (reversed direction)
  function dateToAngle(date) {
    // Calculate months from start date
    const years = date.getFullYear() - startDate.getFullYear();
    const months = date.getMonth() - startDate.getMonth();
    const totalMonthsFromStart = years * 12 + months;

    // Convert to angle (reversed mapping)
    // Earlier date should give higher angle
    const angle = startAngle + ((totalMonths - 1 - totalMonthsFromStart) / (totalMonths - 1)) * totalAngle;

    return angle;
  }

  // Convert polar to cartesian coordinates
  function polarToCartesian(centerX, centerY, radius, angleInDegrees) {
    const angleInRadians = (angleInDegrees - 90) * Math.PI / 180.0;
    return {
      x: centerX + (radius * Math.cos(angleInRadians)),
      y: centerY + (radius * Math.sin(angleInRadians))
    };
  }

  // Create an SVG path for an arc
  function createArc(x, y, radius, startAngle, endAngle) {
    const start = polarToCartesian(x, y, radius, endAngle);
    const end = polarToCartesian(x, y, radius, startAngle);
    const largeArcFlag = endAngle - startAngle <= 180 ? "0" : "1";

    return [
      "M", start.x, start.y,
      "A", radius, radius, 0, largeArcFlag, 0, end.x, end.y
    ].join(" ");
  }

  // Format the date for display
  function formatDate(date) {
    const months = ['January', 'February', 'March', 'April', 'May', 'June',
      'July', 'August', 'September', 'October', 'November', 'December'
    ];
    return `${months[date.getMonth()]} ${date.getFullYear()}`;
  }

  // Update the handle position based on angle
  function updateHandlePosition(angle) {
    const pos = polarToCartesian(center.x, center.y, radius, angle);
    handleElement.setAttribute('cx', pos.x);
    handleElement.setAttribute('cy', pos.y);
  }

  // Update the Dash data store
  function updateDateStore(dateValue) {
    // Find the dcc.Store component by ID and update its data
    const storeElement = document.getElementById('date-slider-value');
    if (storeElement) {
      // This triggers the Dash callback system
      storeElement.dispatchEvent(new CustomEvent('set-data', {
        detail: {
          data: dateValue
        }
      }));
    }
  }

  // Handle mouse/touch events
  function handleStart(event) {
    event.preventDefault();
    isDragging = true;
    handleMove(event);

    // Add move and end event listeners
    document.addEventListener('mousemove', handleMove);
    document.addEventListener('mouseup', handleEnd);
    document.addEventListener('touchmove', handleMove, { passive: false });
    document.addEventListener('touchend', handleEnd);
  }

  function handleEnd() {
    isDragging = false;

    // Remove move and end event listeners
    document.removeEventListener('mousemove', handleMove);
    document.removeEventListener('mouseup', handleEnd);
    document.removeEventListener('touchmove', handleMove);
    document.removeEventListener('touchend', handleEnd);
  }
  
  function screenToSVGCoordinates(event, svgElement) {
    const svgRect = svgElement.getBoundingClientRect();
    const screenX = event.clientX || (event.touches && event.touches[0].clientX);
    const screenY = event.clientY || (event.touches && event.touches[0].clientY);
    
    // Get the SVG's scaling factor
    const scaleFactor = svgRect.width / 600; // 600 is the SVG's viewBox width
    
    // Transform coordinates
    const svgX = (screenX - svgRect.left) / scaleFactor;
    const svgY = (screenY - svgRect.top) / scaleFactor;
    
    return { x: svgX, y: svgY };
  }

  function handleMove(event) {
    if (!isDragging && event.type !== 'mousedown' && event.type !== 'touchstart') return;

    event.preventDefault();

    // Get SVG coordinates
    const svgRect = svgElement.getBoundingClientRect();

    // Get mouse/touch position
    let clientX, clientY;
    if (event.type.startsWith('touch')) {
      clientX = event.touches[0].clientX;
      clientY = event.touches[0].clientY;
    } else {
      clientX = event.clientX;
      clientY = event.clientY;
    }

    // Convert to SVG coordinates
    // const x = clientX - svgRect.left;
// const y = clientY - svgRect.top;
    
    const coords = screenToSVGCoordinates(event, svgElement);
    const x = coords.x;
    const y = coords.y;

    // Calculate angle
    const dx = x - center.x;
    const dy = y - center.y;
    let angle = Math.atan2(dy, dx) * 180 / Math.PI + 90;
    if (angle < 0) angle += 360;

    // Restrict to the valid range
    if (angle < startAngle || angle > endAngle) {
      // Find closest valid angle
      const distToStart = Math.min(Math.abs(angle - startAngle), Math.abs(angle - (startAngle + 360)));
      const distToEnd = Math.min(Math.abs(angle - endAngle), Math.abs(angle - (endAngle - 360)));
      angle = distToStart < distToEnd ? startAngle : endAngle;
    }

    currentAngle = angle;
    currentDate = angleToDate(angle);

    // Update UI
    updateHandlePosition(currentAngle);
    currentDateElement.textContent = formatDate(currentDate);
    updateDateStore(formatDate(currentDate));
  }
}

if (!window.dash_clientside) {
  window.dash_clientside = {};
}

window.dash_clientside.clientside = {
  initializeSlider: function(n_intervals) {
    // Only initialize if we haven't already done so
    if (document.getElementById('slider-svg')) {
      return '';
    }

    const container = document.getElementById('slider');
    if (!container) return '';

    // Create the SVG and all elements
    container.innerHTML = `
            <svg width="600" height="600" id="slider-svg" viewBox="0 0 600 600" preserveAspectRatio="xMidYMid meet">
                <!-- Background circle (inactive part) -->
                <circle cx="300" cy="300" r="270" class="inactive-circle"></circle>
                
                <!-- Active arc (bottom third) -->
                <path id="active-arc" class="active-arc"></path>
                
                <!-- Month ticks and year labels will be added dynamically -->
                <g id="tick-marks"></g>
                <g id="year-labels"></g>
                
                <!-- Slider handle -->
                <circle id="handle" cx="300" cy="300" r="16" class="handle"></circle>
                
                <!-- Center point -->
                <circle cx="300" cy="300" r="4" class="center-point"></circle>
                
                <!-- Date labels -->
                <text id="start-label" class="date-label"></text>
                <text x="300" y="550" text-anchor="middle" class="date-label"></text>
                <text id="end-label" class="date-label"></text>
            </svg>
            <div class="current-date">January 2018</div>
        `;

    // Initialize the slider functionality
    initCircularSlider();

    return '';
  }
};


// 
// On-load event listeners for Map and Slider
//

document.addEventListener('DOMContentLoaded', waitForContainer);
// document.addEventListener('DOMContentLoaded', initCircularSlider);