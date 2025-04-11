window.addEventListener('load', function() {
	console.log('Window loaded - ensuring event handlers are set up');
	setupScrolling();
	// setupInputClearing();
});

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