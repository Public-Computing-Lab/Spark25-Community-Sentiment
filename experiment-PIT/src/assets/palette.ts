export const colorPalette = {
    dark: '#02447C',          // Header, Buttons, Icons, User Msg Background, Map Dots
    background: '#1D90A2',    // General background
    chatBackground: '#CEDDEB',// Chat message background
    mapBorders: '#000000',    // Map borders
    submitArrow: '#CB1616',   // Red submit arrow
    text: "#FFFFFF"
} as const;

export type ColorPalette = typeof colorPalette;
