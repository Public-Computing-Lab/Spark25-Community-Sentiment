/**
 * Key.tsx
 * This file hosts the UI of the tooltips of each data point for the map. 
 */

import { Box, Typography } from '@mui/material';

function Tooltip({
    /**
     * This file hosts the UI of the tooltips of each data point for the map. Varies content by data type
     * Args/Dependencies: type: string, name (optional): string, date (optional): string, alternates (optional): string
     * Returns: N/A
     */
    type,
    name,
    date,
    alternates
}:{
    type: string,
    name?: string,
    date?: string,
    alternates?: string
}) {
 
    const alts = alternates?.split(","); //turning alternate name strings into a list
    console.log(alts)

    if (type == "Community Assets"){
        return (
        <Box
        sx={{
            bgcolor: "white",
            width: "auto",
            height: "auto",
        }}
        >
            <Typography
                sx={{
                    fontSize: "17px",
                    fontWeight: 'bold',
                }}
            >
                {name}
            </Typography>
            <Typography
                sx={{
                    fontSize: "14px",
                }}
            >
                Also known as:
            </Typography>
        
            {alts && alts[0] !== '' ? (
                alts.map((str, key) => (
                    <li key={key}>{str}</li>
                ))
            ) : (
                <Typography sx={{ fontSize: "14px", fontStyle: "italic" }}>
                    No alternate names available.
                </Typography>
            )}
        </Box>
    )

    }
    if (type == "Gun Violence Incidents"){
        return (
             <Box
        sx={{
            bgcolor: "white",
            width: "auto",
            height: "auto",
        }}
        >
            <Typography
                sx={{
                    fontSize: "17px",
                }}
            >
                This incident took place on
            </Typography>
            <Typography
                sx={{
                    fontSize: "14px",
                    fontWeight: 'bold',
                }}
            >
                {date}
            </Typography>
        
        </Box>
        )
    }
    if (type == "311 Requests") {
        return (
             <Box
        sx={{
            bgcolor: "white",
            width: "auto",
            height: "auto",
        }}
        >
            <Typography
                sx={{
                    fontSize: "17px",
                }}
            >
                Request: {name}
            </Typography>
            <Typography
                sx={{
                    fontSize: "15px",
                    fontWeight: 'bold',
                }}
            >
                On {date}
            </Typography>
        
        </Box>
        )
    }
    
}

export default Tooltip;