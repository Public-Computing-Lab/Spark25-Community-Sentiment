export const colorPalette = {
    dark: '#02447C',          // Header, Buttons, Icons, Map Dots
    background: '#E7F4FF',    // App background
    botBubble: '#CEDDEB', // Bot message background
    userBubble: '#315A7C', // User message background 
    textOverBotBubble: '#1c1c1c',
    textOverUserBubble: '#FFFFFF',
    mapBorders: '#000000'   // Map borders

} as const;

export type ColorPalette = typeof colorPalette;
