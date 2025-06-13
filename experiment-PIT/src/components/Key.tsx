import { Box, Typography} from '@mui/material';

function Key() {
    return (
        <Box sx={{
            maxWidth: "40vw",
            width: "30vw",
            height: "15vh",
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
                Legend
            </Typography>
            <Box sx={{ display: 'flex', alignItems: 'center', paddingLeft: '1em' }}>
                <Box sx={{
                    width: '10px',
                    height: '10px',
                    backgroundColor: '#880808', // Red for Shootings
                    borderRadius: '50%',
                    marginRight: '0.4em',
                }} />
                <Typography sx={{ fontSize: "12px" }}>
                    Gun Violence Incidents
                </Typography>
            </Box>
    
            <Box sx={{ display: 'flex', alignItems: 'center', paddingLeft: '1em' }}>
                <Box sx={{
                    width: '10px',
                    height: '10px',
                    backgroundColor: '#228B22', // Red for Shootings
                    borderRadius: '50%',
                    marginRight: '0.4em',
                }} />
                <Typography sx={{ fontSize: "12px" }}>
                    Assets
                </Typography>
            </Box>
            <Box sx={{ display: 'flex', alignItems: 'center', paddingLeft: '1em' }}>
                <Box sx={{
                    width: '10px',
                    height: '10px',
                    backgroundColor: '#FBEC5D', // Red for Shootings
                    borderRadius: '50%',
                    marginRight: '0.5em',
                }} />
                <Typography sx={{ fontSize: "12px" }}>
                    311 Requests
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
