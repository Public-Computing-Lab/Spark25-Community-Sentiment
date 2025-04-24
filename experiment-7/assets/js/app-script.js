(function() {
  'use strict';

  window.updateMapWithDate = function(dateString) {
    console.log(" Direct update attempt for date:", dateString);
    const updateBtn = document.getElementById('update-date-btn');
    console.log(updateBtn)
    if (updateBtn) {
      updateBtn.setAttribute('data-date', dateString);
      updateBtn.click();
      console.log("Updated date via bridge button");
      return true;
    }
    console.warn("Could not find update-date-btn");
    return false;
  };

  const App = {
    config: {
      mapbox: {
        token: window.MAPBOX_TOKEN,
        initialCenter: [-71.07601, 42.28988],
        backgroundInitialZoom: 12,
        magnifiedInitialZoom: 13
      },
      slider: {
        center: { x: 300, y: 300 },
        radius: 270,
        startAngle: 135,
        endAngle: 225,
        startDate: new Date(2018, 0),
        endDate: new Date(2024, 11)
      },
      debounceTime: 3000,
      refreshChatDelay: 500
    },

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

    init() {
      document.addEventListener('DOMContentLoaded', () => {
        this.waitForContainer();
      });
    },

    waitForContainer() {
      const mapsReady = document.getElementById('before-map') &&
        document.getElementById('after-map');
      if (mapsReady) {
        this.MapModule.init();
      } else {
        setTimeout(() => this.waitForContainer(), 100);
      }
    },

    MapModule: {
      init() {
        const config = App.config.mapbox;
        mapboxgl.accessToken = config.token;
        const beforeMap = new mapboxgl.Map({
          container: 'before-map',
          style: 'mapbox://styles/mapbox/light-v11',
          center: config.initialCenter,
          zoom: config.backgroundInitialZoom,
          interactive: true,
        });
        App.state.maps.before = beforeMap;
        window.beforeMap = beforeMap;

        const afterMap = new mapboxgl.Map({
          container: 'after-map',
          style: 'mapbox://styles/mapbox/streets-v12',
          center: config.initialCenter,
          zoom: config.magnifiedInitialZoom,
          interactive: false
        });
        App.state.maps.after = afterMap;
        window.afterMap = afterMap;
        afterMap.on('style.load', () => {
          console.log(' afterMap style fully loaded');
          this.setupDataLayers(afterMap);
          const hexStore = document.getElementById('hexbin-data-store');
          const shotsStore = document.getElementById('shots-data-store');
          const homStore = document.getElementById('homicides-data-store');
          if (hexStore && hexStore._dashprivate_store) {
            const hexData = hexStore._dashprivate_store.data;
            const shotsData = shotsStore._dashprivate_store.data;
            const homData = homStore._dashprivate_store.data;
            if (hexData || shotsData || homData) {
              App.MapModule.updateMapData(hexData, shotsData, homData);
              console.log('♻️ Initial map data applied');
            }
          }
        });

        this.setupEventHandlers(beforeMap, afterMap);
      },

      /**
       * Set up map event handlers
       * @param {Object} beforeMap 
       * @param {Object} afterMap 
       */
      setupEventHandlers(beforeMap, afterMap) {
        beforeMap.on('move', () => {
          afterMap.jumpTo({
            center: beforeMap.getCenter(),
            zoom: beforeMap.getZoom() + 1,
            bearing: beforeMap.getBearing(),
            pitch: beforeMap.getPitch()
          });
        });

        beforeMap.on('load', () => {
          beforeMap.addSource('hexDataBackground', {
            type: 'geojson',
            data: { type: 'FeatureCollection', features: [] }
          });
          beforeMap.addLayer({
            id: 'hexLayerBackground',
            type: 'fill',
            source: 'hexDataBackground',
            paint: {
              'fill-color': [
                'interpolate', ['linear'],
                ['get', 'value'],
                0, 'rgba(0,0,0,0)',
                1, '#eeeeee', 5, '#cccccc', 10, '#999999', 20, '#666666'
              ],
              'fill-opacity': 0.5,
              'fill-outline-color': 'rgba(200,200,200,0.5)'
            }
          });
        });
        beforeMap.on('moveend', () => this.handleMapMoveEnd(beforeMap, afterMap));
      },

      /**
       * Set up data layers on the visualization map
       * @param {Object} map 
       */
      setupDataLayers(map) {
        console.log("Setting up map data layers");
        if (map.getSource('hexData')) {
          console.log("Data sources already exist, updating them instead of creating new ones");
          return;
        }
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
              'case',
              ['==', ['get', 'value'], null], '#cccccc',
              ['interpolate', ['linear'],
                ['get', 'value'],
                0, 'rgba(0,0,0,0)',
                1, '#fdebcf',
                5, '#f08e3e',
                10, '#b13d14',
                20, '#70250F'
              ]
            ],
            'fill-opacity': 0.8,
            'fill-outline-color': 'rgba(255,255,255,0.6)'
          }

        });

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
       * @param {Object} beforeMap 
       * @param {Object} afterMap 
       */
      handleMapMoveEnd(beforeMap, afterMap) {
        clearTimeout(App.state.maps.moveTimeout);

        App.state.maps.moveTimeout = setTimeout(() => {
          const center = beforeMap.getCenter();
          const zoom = beforeMap.getZoom() + 1;
          const features = afterMap.queryRenderedFeatures({ layers: ['hexLayer'] });
          const baseRad = 0.015 * Math.pow(2, 13 - zoom);
          const hexIDs = [];
          const eventIDs = [];
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
          console.log("Map view updated - visible hexes:", hexIDs.length, "events:", eventIDs.length);
          this.updateDashAttributes(hexIDs, eventIDs);
        }, App.config.debounceTime);
      },

      /**
       * Update Dash attributes with collected data
       * @param {Array} hexIDs 
       * @param {Array} eventIDs
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
        setTimeout(() => {
          const refreshBtn = document.getElementById('refresh-chat-btn');
          if (refreshBtn) {
            console.log("🔍 Refreshing chat data");
            refreshBtn.click();
          }
        }, App.config.refreshChatDelay);
      }
    },

    SliderModule: {
      elements: null,
      init() {
        const container = document.getElementById('slider');
        if (!container) {
          console.error("Slider container not found");
          return;
        }
        this.createSliderDOM(container);
        this.setupSlider();
      },

      /**
       * Create slider DOM elements
       * @param {HTMLElement} container 
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
          <div class="current-date">December 2024</div>
        `;
      },

      /**
       * Set up the slider functionality
       */
      setupSlider() {
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
            if (month === 0) {
              tickLine.setAttribute('class', 'tick-mark-january');
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

      setupEventListeners() {
        const { elements } = this;
        const handleDragStart = (event) => {
          event.preventDefault();
          App.state.slider.isDragging = true;
          this.handleDragMove(event);
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
          document.removeEventListener('mousemove', handleDragMove);
          document.removeEventListener('mouseup', handleDragEnd);
          document.removeEventListener('touchmove', handleDragMove);
          document.removeEventListener('touchend', handleDragEnd);
        };

        elements.svg.addEventListener('mousedown', handleDragStart);
        elements.svg.addEventListener('touchstart', handleDragStart, { passive: false });
        const handleDateChange = () => {
          const formattedDate = this.utils.formatDate(App.state.slider.currentDate);
          this.updateDateStore(formattedDate);
          console.log("Date changed to:", formattedDate);
          const refreshBtn = document.getElementById('refresh-chat-btn');
          if (refreshBtn) {
            console.log("Forcing chat refresh");
            refreshBtn.click();
          }
        };

        elements.handle.addEventListener('mouseup', handleDateChange);
        document.addEventListener('touchend', function(e) {
          if (App.state.slider.isDragging) {
            handleDateChange();
          }
        });

        const handleSliderChange = () => {
          const dateDisplay = document.querySelector('.current-date');
          if (dateDisplay && dateDisplay.textContent) {
            const dateValue = dateDisplay.textContent.trim();
            window.updateMapWithDate(dateValue);
          }
        };
        elements.handle.addEventListener('click', handleSliderChange);
        elements.handle.addEventListener('touchend', handleSliderChange);
      },
      /**
       * Handle slider drag movement
       * @param {Event} event 
       */
      handleDragMove(event) {
        const { elements } = this;
        const config = App.config.slider;
        const state = App.state.slider;
        const { center, startAngle, endAngle } = config;
        const coords = this.utils.screenToSVGCoordinates(event, elements.svg);
        const dx = coords.x - center.x;
        const dy = coords.y - center.y;
        let angle = Math.atan2(dy, dx) * 180 / Math.PI + 90;
        if (angle < 0) angle += 360;
        if (angle < startAngle || angle > endAngle) {
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

        state.currentAngle = angle;
        state.currentDate = this.utils.angleToDate(angle);

        this.updateHandlePosition(angle);

        const formattedDate = this.utils.formatDate(state.currentDate);
        elements.currentDate.textContent = formattedDate;

        const dateStr = formattedDate.replace(' ', '-');
        console.log("🔄 Date changed to:", formattedDate);

      },
      /**
       * Update the position of the slider handle
       * @param {Number} angle 
       */

      updateHandlePosition(angle) {
        const { center, radius } = App.config.slider;
        const pos = this.utils.polarToCartesian(center.x, center.y, radius, angle);
        this.elements.handle.setAttribute('cx', pos.x);
        this.elements.handle.setAttribute('cy', pos.y);
      },

      updateDateStore(dateValue) {
        const selectors = [
          '[data-dash-is-loading="false"][id="date-slider-value"]',
          '#date-slider-value',
          '[id="date-slider-value"]'
        ];

        let storeElement = null;
        for (const selector of selectors) {
          const element = document.querySelector(selector);
          if (element) {
            storeElement = element;
            break;
          }
        }

        if (!storeElement) {
          console.warn("Could not find date-slider-value, will retry later");
          setTimeout(() => this.updateDateStore(dateValue), 500);
          return;
        }

        storeElement.textContent = dateValue;
        const event = new CustomEvent("set-data", {
          detail: { data: dateValue }
        });
        storeElement.dispatchEvent(event);
        if (storeElement._dashprivate_setProps) {
          storeElement._dashprivate_setProps({ data: dateValue });
        }

        const updateBtn = document.getElementById('update-date-btn');
        if (updateBtn) {
          updateBtn.setAttribute('data-date', dateValue);
          updateBtn.click();
        }

        console.log(" Triggered Dash Store update for:", dateValue);
      },

      /**
       * Utility functions for the slider
       */
      utils: {
        /**
         * Convert angle to date
         * @param {Number} angle 
         * @returns {Date} 
         */
        angleToDate(angle) {
          const config = App.config.slider;
          const { startAngle, endAngle, startDate } = config;
          const totalAngle = endAngle - startAngle;
          const totalMonths = this.getTotalMonths(config.startDate, config.endDate) + 1;
          const normalizedAngle = angle - startAngle;
          const monthIndex = Math.round(
            ((totalAngle - normalizedAngle) / totalAngle) * (totalMonths - 1)
          );

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
          const years = date.getFullYear() - startDate.getFullYear();
          const months = date.getMonth() - startDate.getMonth();
          const totalMonthsFromStart = years * 12 + months;
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

          const clientX = event.clientX || (event.touches && event.touches[0].clientX);
          const clientY = event.clientY || (event.touches && event.touches[0].clientY);
          const scaleFactor = svgRect.width / 600;
          return {
            x: (clientX - svgRect.left) / scaleFactor,
            y: (clientY - svgRect.top) / scaleFactor
          };
        },
      },
    },
  };

  /**
   * Dash Clientside Callbacks
   */
  window.dash_clientside = window.dash_clientside || {};
  window.dash_clientside.clientside = {

    initializeSlider: function(n_intervals) {
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
      console.log("Map update triggered with features:",
        hexData ? (hexData.features ? hexData.features.length : 0) : "no data"
      );

      function tryUpdateMap(attempts = 0) {
        if (attempts >= 5) {
          console.error("Failed to update map after multiple attempts");
          return;
        }

        const map = window.afterMap;
        if (!map || !map.isStyleLoaded()) {
          console.warn("afterMap or style not ready, retrying...");
          setTimeout(() => tryUpdateMap(attempts + 1), 500);
          return;
        }

        console.log("Has hex layer?", map.getLayer("hexLayer"));

        const ensureSource = (id) => {
          const source = map.getSource(id);
          if (!source) {
            console.warn(`Source '${id}' missing, setting up layers again`);
            if (window.App && App.MapModule && App.MapModule.setupDataLayers) {
              App.MapModule.setupDataLayers(map);
            }
            return map.getSource(id);
          }
          return source;
        };

        const hexSource = ensureSource("hexData");
        const shotsSource = ensureSource("shotsData");
        const homSource = ensureSource("homicidesData");

        if (!hexSource || !shotsSource || !homSource) {
          console.warn("Sources still missing, retrying...");
          setTimeout(() => tryUpdateMap(attempts + 1), 500);
          return;
        }

        try {
          if (hexData) {
            console.log("HexData[0]:", JSON.stringify(hexData.features[0], null, 2));

            hexSource.setData(hexData);
            console.log("Updated hexbin data with", hexData.features.length, "features");
          }
          if (shotsData) {
            shotsSource.setData(shotsData);
            console.log("Updated shots data");
          }
          if (homData) {
            homSource.setData(homData);
            console.log("Updated homicides data");
          }

          if (window.beforeMap && window.beforeMap.isStyleLoaded()) {
            const bgSource = window.beforeMap.getSource("hexDataBackground");
            if (bgSource && hexData) {
              bgSource.setData(hexData);
              console.log("Updated background map");
            }
          }
        } catch (err) {
          console.error("Error updating map sources:", err);
          setTimeout(() => tryUpdateMap(attempts + 1), 500);
        }
      }

      tryUpdateMap();
      return '';
    }

  };

  App.SliderModule.init = App.SliderModule.init.bind(App.SliderModule);
  App.SliderModule.setupSlider = App.SliderModule.setupSlider.bind(App.SliderModule);
  App.SliderModule.drawSliderUI = App.SliderModule.drawSliderUI.bind(App.SliderModule);
  App.SliderModule.handleDragMove = App.SliderModule.handleDragMove.bind(App.SliderModule);
  App.init();
})();

window.clientside = {
  ...window.clientside,

  scrollChatLeft: function(children) {
    const wrap = document.querySelector('#chat-section-left .chat-messages-wrapper');
    if (wrap) { wrap.scrollTop = wrap.scrollHeight; }
    return '';
  },

  scrollChatRight: function(children) {
    const wrap = document.querySelector('#chat-section-right .chat-messages-wrapper');
    if (wrap) { wrap.scrollTop = wrap.scrollHeight; }
    return '';
  },
};