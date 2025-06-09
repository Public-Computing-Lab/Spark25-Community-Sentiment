import { Box, Typography} from '@mui/material';

function Key() {
    return (
        <Box sx={{
            maxWidth: "50vw",
            width: "20vw",
            height: "13vh",
            bgcolor: 'white',
            boxShadow: "0 2px 4px rgba(0, 0, 0, 0.1)",
            '&:hover': {
                 boxShadow: "0 2px 4px rgba(0, 0, 0, 0.4)",
            },
            borderRadius: 3,
            borderWidth: 3,
            margin: '1em',
        }}>
            <Typography sx={{
                padding: '0.5em',
                fontWeight: 'bold',
            }}>
                Data Legend
            </Typography>
            <Box sx={{ display: 'flex', alignItems: 'center', paddingLeft: '1em' }}>
                <Box sx={{
                    width: '10px',
                    height: '10px',
                    backgroundColor: '#880808', // Red for Shootings
                    borderRadius: '50%',
                    marginRight: '0.5em',
                }} />
                <Typography sx={{ fontSize: "12px" }}>
                    Shootings
                </Typography>
            </Box>
    
            <Box sx={{ display: 'flex', alignItems: 'center', paddingLeft: '1em' }}>
                <Box sx={{
                    width: '10px',
                    height: '10px',
                    backgroundColor: '#228B22', // Red for Shootings
                    borderRadius: '50%',
                    marginRight: '0.5em',
                }} />
                <Typography sx={{ fontSize: "12px" }}>
                    Community Assets
                </Typography>
            </Box>
            <Box sx={{ display: 'flex', alignItems: 'center', paddingLeft: '1em' }}>
                <Box sx={{
                    width: '10px',
                    height: '5px',
                    backgroundColor: '#82aae7', // Red for Shootings
                    borderRadius: '0',
                    marginRight: '0.5em',
                }} />
                <Typography sx={{ fontSize: "12px" }}>
                    TNT Border
                </Typography>
            </Box>
        </Box>

    )
        
}

export default Key;
