// Function to set up scroll behavior
function setupScrolling() {
	// Create a global variable to track the last scroll trigger value
	window.lastScrollTrigger = '';

	// Set up an interval to check if the scroll trigger has changed
	setInterval(function() {
		const scrollTrigger = document.getElementById('scroll-trigger');
		if (scrollTrigger && scrollTrigger.textContent !== window.lastScrollTrigger) {
			console.log('Scroll trigger changed, scrolling chat to bottom');
			// Update our tracking variable
			window.lastScrollTrigger = scrollTrigger.textContent;

			// Scroll the chat to the bottom
			const chatWrapper = document.querySelector('.chat-messages-wrapper');
			if (chatWrapper) {
				chatWrapper.scrollTop = chatWrapper.scrollHeight;

				// Also try again after a short delay to catch any rendering delays
				setTimeout(function() {
					chatWrapper.scrollTop = chatWrapper.scrollHeight;
				}, 100);
			}
		}
	}, 50); // Check frequently
}

function debounce(func, wait) {
	let timeout;
	return function() {
		const context = this;
		const args = arguments;
		clearTimeout(timeout);
		timeout = setTimeout(() => {
			func.apply(context, args);
		}, wait);
	};
}

// Trigger resize event handling
const triggerResize = debounce(function() {
	const resizeTrigger = document.getElementById('window-resize-trigger');
	if (resizeTrigger) {
		// Increment n_clicks to trigger the callback
		if (!resizeTrigger._clickCount) resizeTrigger._clickCount = 0;
		resizeTrigger._clickCount++;
		resizeTrigger.setAttribute('n_clicks', resizeTrigger._clickCount);

		// Create and dispatch a custom event
		const event = new CustomEvent('resize_update');
		resizeTrigger.dispatchEvent(event);
	}
}, 250);

// Add event listener for window resize
window.addEventListener('resize', triggerResize);

// Trigger initially after a short delay to ensure proper setup
setTimeout(triggerResize, 100);

// Make sure the window dimensions are calculated on load
window.addEventListener('load', function() {
	console.log("Window loaded, triggering initial resize");
	triggerResize();
	setupScrolling();
});

// Also trigger on DOMContentLoaded for earlier responsiveness
document.addEventListener('DOMContentLoaded', function() {
	console.log("DOM content loaded, triggering initial resize");
	triggerResize();
	setupScrolling();
});