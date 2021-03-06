#!/usr/bin/env python3

# Load after `source activate fcnd` has been issued.

import argparse
import time
from enum import Enum

import numpy as np

from udacidrone import Drone
from udacidrone.connection import MavlinkConnection, WebSocketConnection  # noqa: F401
from udacidrone.messaging import MsgID


class States(Enum):
    MANUAL = 0
    ARMING = 1
    TAKEOFF = 2
    WAYPOINT = 3
    LANDING = 4
    DISARMING = 5


class BackyardFlyer(Drone):

    def __init__(self, connection):
        super().__init__(connection)

        self.square_arm = 5.0

        self.target_position = np.array([0.0, 0.0, 0.0])
        self.all_waypoints = [np.array([0.0, 0.0, 3.0]),
                              np.array([self.square_arm, 0.0, 3.0]),
                              np.array([self.square_arm, self.square_arm, 3.0]),
                              np.array([0.0, self.square_arm, 3.0]),
                              np.array([0.0, 0.0, 3.0])]
        self.in_mission = True
        self.check_state = {}
        self.just_taken_off = False

        # initial state
        self.flight_state = States.MANUAL

        # Registering callbacks:
        self.register_callback(MsgID.LOCAL_POSITION, self.local_position_callback)
        self.register_callback(MsgID.LOCAL_VELOCITY, self.velocity_callback)
        self.register_callback(MsgID.STATE, self.state_callback)

    def local_position_callback(self):
        """
        This triggers when `MsgID.LOCAL_POSITION` is received and self.local_position contains new data
        """

        print("Local position callback")

        north    = self.target_position[0]
        east     = self.target_position[1]
        altitude = self.target_position[2]

        self.show_diagnostics()

        # Convert cordinates
        if self.flight_state == States.TAKEOFF:

            altitude = -1.0 * self.local_position[2]

            # Check if altitude is within acceptable range from the target.
            if altitude > 0.95 * self.target_position[2]:
                self.just_taken_off = True
                self.waypoint_transition()

        elif self.flight_state == States.WAYPOINT:
            if len(self.all_waypoints) == 0 and self.reached_destination():
                self.landing_transition()

            elif self.reached_destination():
                self.waypoint_transition()

            if False: #self.reached_destination():
#               if self.just_taken_off == True:
#                   #self.waypoint_transition()
#                   self.just_taken_off = False
#               else:
                self.waypoint_transition()

    def show_diagnostics(self):
        """
        Show current flight parameters.
        """

        print("Flight state: ", self.flight_state)
        print("Target position: ", self.target_position)
        print("Current position: ", self.local_position)
        print("Reached destination? ", self.reached_destination())

    def reached_destination(self):
        """
        Checks if current position meets destination criteria.
        """

        north = 1.0 * self.local_position[0]
        east = 1.0 * self.local_position[1]
        altitude = -1.0 * self.local_position[2]

        if abs(north - self.target_position[0]) < 0.2 and \
           abs(east - self.target_position[1]) < 0.2 and \
           abs(altitude - self.target_position[2]) < 0.2:
            return True
        else:
            return False

    def velocity_callback(self):
        """
        This triggers when `MsgID.LOCAL_VELOCITY` is received and self.local_velocity contains new data
        """

        print("Velocity callback")

        if self.flight_state == States.LANDING:
            if ((self.global_position[2] - self.global_home[2] < 0.1) and \
                                abs(self.local_position[2]) < 0.01):
               self.disarming_transition()

    def state_callback(self):
        """
        This triggers when `MsgID.STATE` is received and self.armed and self.guided contain new data
        """

        print("State callback")

        if not self.in_mission:
            return
        if self.flight_state == States.MANUAL:
            self.arming_transition()
        elif self.flight_state == States.ARMING:
            if self.armed:
                self.takeoff_transition()
#         elif self.flight_state == States.WAYPOINT:
#             if self.reached_destination():
#                 if len(self.all_waypoints) == 0:
#                     self.landing_transition()
#                 else:
#                     self.waypoint_transition()
        elif self.flight_state == States.LANDING:
            if self.armed and -1.0 * self.local_position[2] < 0.3:
                self.disarming_transition()
        elif self.flight_state == States.DISARMING:
            if not self.armed:
                self.manual_transition()

    def calculate_box(self):
        """
        1. Return waypoints to fly a box
        """

        return self.all_waypoints

    def arming_transition(self):
        """
        1. Take control of the drone
        2. Pass an arming command
        3. Set the home location to current position
        4. Transition to the ARMING state
        """
        print("arming transition")

        self.take_control()
        self.arm()

        self.set_home_position(self.global_position[0],
                               self.global_position[1],
                               self.global_position[2])
        self.flight_state = States.ARMING

    def takeoff_transition(self):
        """
        1. Set target_position altitude to 3.0m
        2. Command a takeoff to 3.0m
        3. Transition to the TAKEOFF state
        """
        print("takeoff transition")

        target_altitude = 3.0
        self.target_position[2] = target_altitude
        self.takeoff(target_altitude)
        self.flight_state = States.TAKEOFF

    def waypoint_transition(self):
        """
        1. Command the next waypoint position
        2. Transition to WAYPOINT state
        """
        print("waypoint transition")

        if len(self.all_waypoints) == 0:
            self.landing_transition()

        self.target_position = self.all_waypoints.pop()
        print(self.target_position)

        self.cmd_position(self.target_position[0],
                          self.target_position[1],
                          self.target_position[2],
                          0)
        self.flight_state = States.WAYPOINT

    def landing_transition(self):
        """
        1. Command the drone to land
        2. Transition to the LANDING state
        """
        print("landing transition")

        self.land()
        self.flight_state = States.LANDING

    def disarming_transition(self):
        """
        1. Command the drone to disarm
        2. Transition to the DISARMING state
        """
        print("disarm transition")

        self.disarm()
        self.flight_state = States.DISARMING

    def manual_transition(self):
        """
        1. Release control of the drone
        2. Stop the connection (and telemetry log)
        3. End the mission
        4. Transition to the MANUAL state
        """
        print("manual transition")

        self.release_control()
        self.stop()
        self.in_mission = False
        self.flight_state = States.MANUAL

    def start(self):
        """
        1. Open a log file
        2. Start the drone connection
        3. Close the log file
        """
        print("Creating log file")
        self.start_log("Logs", "NavLog.txt")
        print("starting connection")
        self.connection.start()
        print("Closing log file")
        self.stop_log()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=5760, help='Port number')
    parser.add_argument('--host', type=str, default='127.0.0.1', help="host address, i.e. '127.0.0.1'")
    args = parser.parse_args()

    conn = MavlinkConnection('tcp:{0}:{1}'.format(args.host, args.port), threaded=False, PX4=False)
    #conn = WebSocketConnection('ws://{0}:{1}'.format(args.host, args.port))
    drone = BackyardFlyer(conn)
    time.sleep(2)
    drone.start()
