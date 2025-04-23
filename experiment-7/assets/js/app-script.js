(function() {
  'use strict';

  // Application namespace
  const App = {
    // Configuration
    config: {
      mapbox: {
        token: window.MAPBOX_TOKEN,
        initialCenter: [-71.07601, 42.28988],
        initialZoom: 13
      },
      slider: {
        center: { x: 300, y: 300 },
        radius: 270,
        startAngle: 135,
        endAngle: 225,
        startDate: new Date(2018, 0), // January 2018
        endDate: new Date(2024, 11) // December 2024
      },
      debounceTime: 3000,
      refreshChatDelay: 500
    },

    // State management
    state: {
      maps: {
        before: null,
        after: null,
        moveTimeout: null
      },
      slider: {
        currentAngle: null,
        isDragging: false,
        currentDate: null
      }
    },

    /**
     * Initialize the application
     */
    init() {
      document.addEventListener('DOMContentLoaded', () => {
        this.waitForContainer();
      });
    },

    /**
     * Wait for required DOM elements before initialization
     */
    waitForContainer() {
      const mapsReady = document.getElementById('before-map') &&
        document.getElementById('after-map');

      if (mapsReady) {
        this.MapModule.init();
      } else {
        setTimeout(() => this.waitForContainer(), 100);
      }
    },

    /**
     * Map Module - Handles map rendering and interactions
     */
    MapModule: {
      /**
       * Initialize maps
       */
      init() {
        const config = App.config.mapbox;
        mapboxgl.accessToken = config.token;

        // Initialize the background map (interactive)
        const beforeMap = new mapboxgl.Map({
          container: 'before-map',
          style: 'mapbox://styles/mapbox/light-v11',
          center: config.initialCenter,
          zoom: config.initialZoom,
          interactive: true,
        });
        App.state.maps.before = beforeMap;
        window.beforeMap = beforeMap;

        // Initialize the data visualization map (non-interactive)
        const afterMap = new mapboxgl.Map({
          container: 'after-map',
          style: 'mapbox://styles/mapbox/streets-v12',
          center: config.initialCenter,
          zoom: config.initialZoom,
          interactive: false
        });
        App.state.maps.after = afterMap;
        window.afterMap = afterMap;

        // Set up map event handlers
        this.setupEventHandlers(beforeMap, afterMap);
      },

      /**
       * Set up map event handlers
       * @param {Object} beforeMap - The interactive map
       * @param {Object} afterMap - The data visualization map
       */
      setupEventHandlers(beforeMap, afterMap) {
        // Sync maps on move
        beforeMap.on('move', () => {
          afterMap.jumpTo({
            center: beforeMap.getCenter(),
            zoom: beforeMap.getZoom(),
            bearing: beforeMap.getBearing(),
            pitch: beforeMap.getPitch()
          });
        });

        // Add data layers when map loads
        afterMap.on('load', () => this.setupDataLayers(afterMap));

        // Handle map movement end
        beforeMap.on('moveend', () => this.handleMapMoveEnd(beforeMap, afterMap));
      },

      /**
       * Set up data layers on the visualization map
       * @param {Object} map - The map to add layers to
       */
      setupDataLayers(map) {
        // Add hexagon data layer
        map.addSource('hexData', {
          type: 'geojson',
          data: { type: 'FeatureCollection', features: [] }
        });
        map.addLayer({
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

        // Add shots fired data layer
        map.addSource('shotsData', {
          type: 'geojson',
          data: { type: 'FeatureCollection', features: [] }
        });
        map.addLayer({
          id: 'shotsLayer',
          type: 'circle',
          source: 'shotsData',
          paint: {
            'circle-radius': 7,
            'circle-color': '#A43800',
            'circle-opacity': 0.9
          }
        });

        // Add homicides data layer
        map.addSource('homicidesData', {
          type: 'geojson',
          data: { type: 'FeatureCollection', features: [] }
        });
        map.addLayer({
          id: 'homicidesLayer',
          type: 'circle',
          source: 'homicidesData',
          paint: {
            'circle-radius': 7,
            'circle-color': '#232E33',
            'circle-opacity': 0.9
          }
        });
      },

      /**
       * Handle map movement end and extract visible data
       * @param {Object} beforeMap - The interactive map
       * @param {Object} afterMap - The data visualization map
       */
      handleMapMoveEnd(beforeMap, afterMap) {
        clearTimeout(App.state.maps.moveTimeout);

        App.state.maps.moveTimeout = setTimeout(() => {
          const center = beforeMap.getCenter();
          const zoom = beforeMap.getZoom();
          const features = afterMap.queryRenderedFeatures({ layers: ['hexLayer'] });
          const baseRad = 0.015 * Math.pow(2, 13 - zoom);

          const hexIDs = [];
          const eventIDs = [];

          // Collect features within visible area
          features.forEach(feature => {
            const properties = feature.properties;
            if (!properties?.hex_id) return;

            const dLat = properties.lat - center.lat;
            const dLon = properties.lon - center.lng;
            const distance = Math.sqrt(dLat * dLat + dLon * dLon);

            if (distance <= baseRad) {
              hexIDs.push(properties.hex_id);

              if (properties.ids) {
                let idList = properties.ids;
                if (typeof idList === 'string') {
                  try {
                    idList = JSON.parse(idList);
                  } catch (e) {
                    console.warn("Invalid properties.ids JSON", idList);
                    idList = [];
                  }
                }
                eventIDs.push(...idList);
              }
            }
          });

          console.log("🔍 Map view updated - visible hexes:", hexIDs.length, "events:", eventIDs.length);
          this.updateDashAttributes(hexIDs, eventIDs);
        }, App.config.debounceTime);
      },

      /**
       * Update Dash attributes with collected data
       * @param {Array} hexIDs - Collected hexagon IDs
       * @param {Array} eventIDs - Collected event IDs
       */
      updateDashAttributes(hexIDs, eventIDs) {
        const mapBtn = document.getElementById('map-move-btn');
        if (!mapBtn) {
          console.error("map-move-btn not found in DOM");
          return;
        }

        mapBtn.setAttribute('data-hexids', hexIDs.join(','));
        mapBtn.setAttribute('data-ids', eventIDs.join(','));
        mapBtn.click();

        // Refresh chat after a short delay
        setTimeout(() => {
          const refreshBtn = document.getElementById('refresh-chat-btn');
          if (refreshBtn) {
            console.log("🔍 Refreshing chat data");
            refreshBtn.click();
          }
        }, App.config.refreshChatDelay);
      }
    },

    /**
     * Slider Module - Handles circular date slider
     */
    SliderModule: {
      // DOM elements cache
      elements: null,

      /**
       * Initialize the circular date slider
       */
      init() {
        const container = document.getElementById('slider');
        if (!container) {
          console.error("Slider container not found");
          return;
        }

        // Create the SVG structure
        this.createSliderDOM(container);

        // Initialize the slider functionality
        this.setupSlider();
      },

      /**
       * Create slider DOM elements
       * @param {HTMLElement} container - Container for the slider
       */
      createSliderDOM(container) {
        container.innerHTML = `
          <svg width="600" height="600" id="slider-svg" viewBox="0 0 600 600" preserveAspectRatio="xMidYMid meet">
            <!-- Background circle -->
            <circle cx="300" cy="300" r="270" class="inactive-circle"></circle>
            
            <!-- Active arc -->
            <path id="active-arc" class="active-arc"></path>
            
            <!-- Tick marks and labels containers -->
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
      },

      /**
       * Set up the slider functionality
       */
      setupSlider() {
        // Cache DOM elements
        this.elements = {
          svg: document.getElementById('slider-svg'),
          handle: document.getElementById('handle'),
          activeArc: document.getElementById('active-arc'),
          startLabel: document.getElementById('start-label'),
          endLabel: document.getElementById('end-label'),
          tickMarks: document.getElementById('tick-marks'),
          yearLabels: document.getElementById('year-labels'),
          currentDate: document.querySelector('.current-date')
        };

        // Config shortcuts
        const config = App.config.slider;
        const state = App.state.slider;

        // Initialize state
        state.currentAngle = config.startAngle;
        state.currentDate = new Date(config.startDate);
        state.isDragging = false;

        // Initialize the slider UI
        this.drawSliderUI();

        // Set up event listeners
        this.setupEventListeners();
      },

      /**
       * Draw the slider UI elements
       */
      drawSliderUI() {
        const { elements } = this;
        const config = App.config.slider;
        const { center, radius, startAngle, endAngle } = config;

        // Draw the active arc
        elements.activeArc.setAttribute('d',
          this.utils.createArc(center.x, center.y, radius, startAngle, endAngle)
        );

        // Position start and end labels
        const startPos = this.utils.polarToCartesian(center.x, center.y, radius + 30, startAngle);
        elements.startLabel.setAttribute('x', startPos.x);
        elements.startLabel.setAttribute('y', startPos.y);
        elements.startLabel.textContent = "2018"; // Start label

        const endPos = this.utils.polarToCartesian(center.x, center.y, radius + 30, endAngle);
        elements.endLabel.setAttribute('x', endPos.x);
        elements.endLabel.setAttribute('y', endPos.y);
        elements.endLabel.textContent = "2024"; // End label

        // Create tick marks and year labels
        this.createTickMarksAndLabels();

        // Position handle at initial position
        this.updateHandlePosition(App.state.slider.currentAngle);
      },

      /**
       * Create tick marks for months and labels for years
       */
      createTickMarksAndLabels() {
        const { elements } = this;
        const config = App.config.slider;
        const { center, radius, startDate, endDate } = config;

        elements.tickMarks.innerHTML = '';
        elements.yearLabels.innerHTML = '';

        // Calculate total months in range
        const totalMonths = this.utils.getTotalMonths(startDate, endDate) + 1;

        // For each month in the range
        for (let year = 2018; year <= 2024; year++) {
          for (let month = 0; month < 12; month++) {
            // Skip months outside our range
            if (year === 2024 && month > 11) continue;

            const date = new Date(year, month);
            const angle = this.utils.dateToAngle(date);

            // Create tick mark
            const innerPos = this.utils.polarToCartesian(center.x, center.y, radius - 10, angle);
            const outerPos = this.utils.polarToCartesian(center.x, center.y, radius + 10, angle);

            const tickLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
            tickLine.setAttribute('x1', innerPos.x);
            tickLine.setAttribute('y1', innerPos.y);
            tickLine.setAttribute('x2', outerPos.x);
            tickLine.setAttribute('y2', outerPos.y);

            // January gets a thicker tick mark and year label
            if (month === 0) {
              tickLine.setAttribute('class', 'tick-mark-january');

              // Add year label for January
              const labelPos = this.utils.polarToCartesian(center.x, center.y, radius + 25, angle);

              const yearLabel = document.createElementNS('http://www.w3.org/2000/svg', 'text');
              yearLabel.setAttribute('x', labelPos.x);
              yearLabel.setAttribute('y', labelPos.y);
              yearLabel.setAttribute('class', 'year-label');
              yearLabel.textContent = year;

              elements.yearLabels.appendChild(yearLabel);
            } else {
              tickLine.setAttribute('class', 'tick-mark');
            }

            elements.tickMarks.appendChild(tickLine);
          }
        }
      },

      /**
       * Set up event listeners for slider interaction
       */
      setupEventListeners() {
        const { elements } = this;

        const handleDragStart = (event) => {
          event.preventDefault();
          App.state.slider.isDragging = true;
          this.handleDragMove(event);

          // Add global event listeners
          document.addEventListener('mousemove', handleDragMove);
          document.addEventListener('mouseup', handleDragEnd);
          document.addEventListener('touchmove', handleDragMove, { passive: false });
          document.addEventListener('touchend', handleDragEnd);
        };

        const handleDragMove = (event) => {
          if (!App.state.slider.isDragging &&
            event.type !== 'mousedown' &&
            event.type !== 'touchstart') return;

          event.preventDefault();
          this.handleDragMove(event);
        };

        const handleDragEnd = () => {
          App.state.slider.isDragging = false;

          // Remove global event listeners
          document.removeEventListener('mousemove', handleDragMove);
          document.removeEventListener('mouseup', handleDragEnd);
          document.removeEventListener('touchmove', handleDragMove);
          document.removeEventListener('touchend', handleDragEnd);
        };

        // Attach events to the SVG element
        elements.svg.addEventListener('mousedown', handleDragStart);
        elements.svg.addEventListener('touchstart', handleDragStart, { passive: false });
      },

      /**
       * Handle slider drag movement
       * @param {Event} event - Mouse or touch event
       */
      handleDragMove(event) {
        const { elements } = this;
        const config = App.config.slider;
        const state = App.state.slider;
        const { center, startAngle, endAngle } = config;

        // Get SVG coordinates from screen coordinates
        const coords = this.utils.screenToSVGCoordinates(event, elements.svg);

        // Calculate angle from coordinates
        const dx = coords.x - center.x;
        const dy = coords.y - center.y;
        let angle = Math.atan2(dy, dx) * 180 / Math.PI + 90;
        if (angle < 0) angle += 360;

        // Restrict to the valid arc range
        if (angle < startAngle || angle > endAngle) {
          // Find closest valid angle
          const distToStart = Math.min(
            Math.abs(angle - startAngle),
            Math.abs(angle - (startAngle + 360))
          );
          const distToEnd = Math.min(
            Math.abs(angle - endAngle),
            Math.abs(angle - (endAngle - 360))
          );
          angle = distToStart < distToEnd ? startAngle : endAngle;
        }

        // Update state
        state.currentAngle = angle;
        state.currentDate = this.utils.angleToDate(angle);

        // Update UI
        this.updateHandlePosition(angle);

        // Format and display the current date
        const formattedDate = this.utils.formatDate(state.currentDate);
        elements.currentDate.textContent = formattedDate;

        // Update Dash store
        this.updateDateStore(formattedDate);
      },

      /**
       * Update the position of the slider handle
       * @param {Number} angle - Angle in degrees
       */
      updateHandlePosition(angle) {
        const { elements } = this;
        const { center, radius } = App.config.slider;

        const pos = this.utils.polarToCartesian(center.x, center.y, radius, angle);
        elements.handle.setAttribute('cx', pos.x);
        elements.handle.setAttribute('cy', pos.y);
      },

      /**
       * Update the Dash data store with the new date
       * @param {String} dateValue - Formatted date string
       */
      updateDateStore(dateValue) {
        const storeElement = document.getElementById('date-slider-value');
        if (!storeElement) {
          console.warn("date-slider-value store element not found");
          return;
        }

        // Trigger Dash callback system
        storeElement.dispatchEvent(new CustomEvent('set-data', {
          detail: { data: dateValue }
        }));
      },

      /**
       * Utility functions for the slider
       */
      utils: {
        /**
         * Convert angle to date
         * @param {Number} angle - Angle in degrees
         * @returns {Date} Corresponding date
         */
        angleToDate(angle) {
          const config = App.config.slider;
          const { startAngle, endAngle, startDate } = config;
          const totalAngle = endAngle - startAngle;
          const totalMonths = this.getTotalMonths(config.startDate, config.endDate) + 1;

          // Normalize angle to range [0, totalAngle]
          const normalizedAngle = angle - startAngle;

          // Convert to month index with reversed mapping
          const monthIndex = Math.round(
            ((totalAngle - normalizedAngle) / totalAngle) * (totalMonths - 1)
          );

          // Create new date
          const newDate = new Date(startDate);
          newDate.setMonth(startDate.getMonth() + monthIndex);

          return newDate;
        },

        /**
         * Convert date to angle
         * @param {Date} date - Date to convert
         * @returns {Number} Angle in degrees
         */
        dateToAngle(date) {
          const config = App.config.slider;
          const { startAngle, endAngle, startDate } = config;
          const totalAngle = endAngle - startAngle;
          const totalMonths = this.getTotalMonths(config.startDate, config.endDate) + 1;

          // Calculate months from start date
          const years = date.getFullYear() - startDate.getFullYear();
          const months = date.getMonth() - startDate.getMonth();
          const totalMonthsFromStart = years * 12 + months;

          // Convert to angle with reversed mapping
          const angle = startAngle +
            ((totalMonths - 1 - totalMonthsFromStart) / (totalMonths - 1)) * totalAngle;

          return angle;
        },

        /**
         * Get total months between two dates
         * @param {Date} startDate - Start date
         * @param {Date} endDate - End date
         * @returns {Number} Number of months
         */
        getTotalMonths(startDate, endDate) {
          return (
            (endDate.getFullYear() - startDate.getFullYear()) * 12 +
            (endDate.getMonth() - startDate.getMonth())
          );
        },

        /**
         * Convert polar coordinates to cartesian
         * @param {Number} centerX - Center X coordinate
         * @param {Number} centerY - Center Y coordinate
         * @param {Number} radius - Radius
         * @param {Number} angleInDegrees - Angle in degrees
         * @returns {Object} Cartesian coordinates {x, y}
         */
        polarToCartesian(centerX, centerY, radius, angleInDegrees) {
          const angleInRadians = (angleInDegrees - 90) * Math.PI / 180.0;
          return {
            x: centerX + (radius * Math.cos(angleInRadians)),
            y: centerY + (radius * Math.sin(angleInRadians))
          };
        },

        /**
         * Create an SVG arc path
         * @param {Number} x - Center X coordinate
         * @param {Number} y - Center Y coordinate
         * @param {Number} radius - Radius
         * @param {Number} startAngle - Start angle in degrees
         * @param {Number} endAngle - End angle in degrees
         * @returns {String} SVG path string
         */
        createArc(x, y, radius, startAngle, endAngle) {
          const start = this.polarToCartesian(x, y, radius, endAngle);
          const end = this.polarToCartesian(x, y, radius, startAngle);
          const largeArcFlag = endAngle - startAngle <= 180 ? "0" : "1";

          return [
            "M", start.x, start.y,
            "A", radius, radius, 0, largeArcFlag, 0, end.x, end.y
          ].join(" ");
        },

        /**
         * Format date for display
         * @param {Date} date - Date to format
         * @returns {String} Formatted date string
         */
        formatDate(date) {
          const months = [
            'January', 'February', 'March', 'April', 'May', 'June',
            'July', 'August', 'September', 'October', 'November', 'December'
          ];
          return `${months[date.getMonth()]} ${date.getFullYear()}`;
        },

        /**
         * Convert screen coordinates to SVG coordinates
         * @param {Event} event - Mouse or touch event
         * @param {SVGElement} svgElement - The SVG element
         * @returns {Object} SVG coordinates {x, y}
         */
        screenToSVGCoordinates(event, svgElement) {
          const svgRect = svgElement.getBoundingClientRect();

          // Get client coordinates from mouse or touch event
          const clientX = event.clientX || (event.touches && event.touches[0].clientX);
          const clientY = event.clientY || (event.touches && event.touches[0].clientY);

          // Calculate scaling factor based on viewBox
          const scaleFactor = svgRect.width / 600; // 600 is SVG viewBox width

          // Transform coordinates
          return {
            x: (clientX - svgRect.left) / scaleFactor,
            y: (clientY - svgRect.top) / scaleFactor
          };
        }
      }
    }
  };

  /**
   * Dash Clientside Callbacks
   */
  window.dash_clientside = window.dash_clientside || {};
  window.dash_clientside.clientside = {
    /**
     * Initialize the circular slider
     */
    initializeSlider: function(n_intervals) {
      // Prevent re-initialization
      if (document.getElementById('slider-svg')) {
        return '';
      }

      App.SliderModule.init();
      return '';
    },

    /**
     * Update map data sources with new GeoJSON data
     */
    updateMapData: function(hexData, shotsData, homData) {
      if (!window.afterMap || !window.afterMap.getSource) {
        console.warn('Map not initialized yet');
        return '';
      }

      try {
        // Update hex data
        let source = window.afterMap.getSource('hexData');
        if (source && hexData) source.setData(hexData);

        // Update shots data
        source = window.afterMap.getSource('shotsData');
        if (source && shotsData) source.setData(shotsData);

        // Update homicides data
        source = window.afterMap.getSource('homicidesData');
        if (source && homData) source.setData(homData);
      } catch (error) {
        console.error('Error updating map data:', error);
      }

      return '';
    }
  };

  // Initialize the application
  App.init();
})();