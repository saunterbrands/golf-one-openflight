/// <reference path="plugins.d.ts" />

// Patched fork of OpenGolfSim/ogs-plugin-openconnect.
//
// The stock plugin bridges launch-monitor SHOTS into OpenGolfSim over the
// OpenConnect V1 API (TCP 921) but never sends the club the other way. This
// fork adds club sync: it subscribes to the OGS plugin SDK's `club` event and
// forwards each club change to the connected launch monitor as an OpenConnect
// V1 "201" player message — which OpenFlight's GSPro connector already parses.
//
// Everything else is byte-for-byte the upstream behavior.

// OpenConnect V1 default port is 921
const PORT = 921;

// Keep track of the launch monitor status to show in the OpenGolfSim UI
const device = { isConnected: false, isReady: false };

// Map an OpenGolfSim club id to a GSPro/OpenConnect V1 club code.
// OGS uses <number><letter> (e.g. "7I", "3W", "5H"); OpenConnect uses
// <letter><number> (e.g. "I7", "W3", "H5"). Driver/wedges/putter pass through.
// Unknown ids are passed through unchanged so the monitor can decide.
function ogsToOpenConnectClub(clubId) {
  if (clubId === undefined || clubId === null) return null;
  const id = String(clubId).trim().toUpperCase();
  if (['DR', 'PW', 'GW', 'SW', 'LW', 'PT'].includes(id)) return id;
  if (id === 'AW') return 'GW';
  const numberLetter = id.match(/^(\d)\s*([WHI])$/); // "7I" -> "I7", "3W" -> "W3"
  if (numberLetter) return numberLetter[2] + numberLetter[1];
  return id; // already "I7"-style, or unrecognized
}

const server = network.createServer((socket) => {
  logging.info('Launch monitor connected via OpenConnect V1');

  device.isConnected = true;
  device.isReady = true;
  shotData.updateDeviceStatus(device);

  // --- Club sync (added) ---------------------------------------------------
  // Forward an OGS club change to the launch monitor as an OpenConnect 201
  // player update. `club` fires whenever the user changes club in OpenGolfSim.
  const onClub = (clubId) => {
    const code = ogsToOpenConnectClub(clubId);
    logging.info(`OGS club changed: ${clubId} -> OpenConnect club ${code}`);
    try {
      socket.write(JSON.stringify({ Code: 201, Message: 'Player updated', Player: { Club: code } }) + '\n');
    } catch (err) {
      logging.error(`Failed to send club update: ${err}`);
    }
  };
  shotData.on('club', onClub);

  const teardown = () => {
    shotData.off('club', onClub);
    device.isConnected = false;
    device.isReady = false;
    shotData.updateDeviceStatus(device);
  };

  socket.on('data', (data) => {
    try {
      // Parse the incoming JSON payload from the launch monitor
      const payloadStr = data.toString('utf8');
      const obj = JSON.parse(payloadStr);

      if (obj.ShotDataOptions) {

        // Update the Launch Monitor Ready state if provided
        if (typeof obj.ShotDataOptions.LaunchMonitorIsReady === 'boolean') {
          device.isReady = obj.ShotDataOptions.LaunchMonitorIsReady;
          shotData.updateDeviceStatus(device);
        }

        // Handle Heartbeats
        if (obj.ShotDataOptions.IsHeartBeat) {
          logging.info('Heartbeat received');
          return;
        }

        // Process Ball/Shot Data
        if (obj.ShotDataOptions.ContainsBallData && obj.BallData) {

          // Map the OpenConnect V1 data to OpenGolfSim's shot format
          const openGolfSimShot = {
            ballSpeed: obj.BallData.Speed,
            verticalLaunchAngle: obj.BallData.VLA,
            horizontalLaunchAngle: obj.BallData.HLA,
            spinSpeed: obj.BallData.TotalSpin,
            spinAxis: obj.BallData.SpinAxis
          };

          logging.info(`Sending shot to OpenGolfSim engine...`);
          shotData.sendShot(openGolfSimShot);

          // Reply with a 200 Success Code per OpenConnect V1 protocol specifications
          const response = {
            Code: 200,
            Message: "Shot received successfully"
          };
          socket.write(JSON.stringify(response) + '\n');
        }
      }
    } catch (error) {
      // Due to TCP streaming, chunks could arrive fragmented.
      // A robust implementation would buffer data until a full JSON object is formed.
      logging.error(`Error processing OpenConnect payload: ${error.message}`);
    }
  });

  socket.on('close', () => {
    logging.info('Launch monitor socket closed');
    teardown();
  });

  socket.on('end', () => {
    logging.info('Launch monitor disconnected');
    teardown();
  });

  socket.on('error', (err) => {
    logging.error(`Socket error: ${err}`);
  });
});

server.on('close', () => {
  logging.info('OpenConnect V1 TCP server closed');
  device.isConnected = false;
  device.isReady = false;
  shotData.updateDeviceStatus(device);
});

system.on('exit', async () => {
  server.close();
  device.isConnected = false;
  device.isReady = false;
  shotData.updateDeviceStatus(device);
});

logging.info('Starting OpenConnect V1 TCP server (with club sync)...');
server.listen(PORT, () => {
  logging.info(`Listening for OpenConnect V1 clients at 127.0.0.1:${PORT}`);
});
