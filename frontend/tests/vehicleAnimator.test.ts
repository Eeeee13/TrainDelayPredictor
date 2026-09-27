import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { setVehicleTargets, getRenderedPosition, resetVehicleAnimations } from '../src/utils/vehicleAnimator';
import { getShapeGeometry, pointAtDistance } from '../src/utils/routeGeometry';
import type { Vehicle } from '../src/domain/types';

const position = (lng: number, lat = 0) => ({ lat, lng });
const vehicle = (id: string, lng: number, time: number, lat = 0) => ({
  id, position: position(lng, lat), lastUpdate: new Date(time).toISOString(),
} as Vehicle);
const rendered = (id: string, time: number) => getRenderedPosition(id, position(0), time).position;
const near = (actual: number, expected: number) => assert.ok(Math.abs(actual - expected) < 1e-8, `${actual} != ${expected}`);
beforeEach(resetVehicleAnimations);

test('duplicate snapshots and metadata updates do not accelerate a moving vehicle', () => {
  setVehicleTargets([vehicle('a', 0, 0)], {}, 0);
  setVehicleTargets([vehicle('a', .001, 2000)], {}, 2000);
  setVehicleTargets([vehicle('a', .001, 2000)], {}, 2100);
  setVehicleTargets([vehicle('a', .001, 2000)], {}, 2200);
  near(rendered('a', 3000).lng, .0005);
});

test('each vehicle uses its own fresh measurement interval, including gaps over four seconds', () => {
  setVehicleTargets([vehicle('a', 0, 0), vehicle('b', 0, 0)], {}, 0);
  setVehicleTargets([vehicle('a', .001, 2000), vehicle('b', 0, 0)], {}, 2000);
  setVehicleTargets([vehicle('a', .002, 4000), vehicle('b', 0, 0)], {}, 4000);
  setVehicleTargets([vehicle('a', .003, 6000), vehicle('b', .003, 6000)], {}, 6000);
  near(rendered('b', 8000).lng, .001);
});

test('stationary fresh readings do not restart the remaining animation', () => {
  setVehicleTargets([vehicle('a', 0, 0)], {}, 0);
  setVehicleTargets([vehicle('a', .001, 2000)], {}, 2000);
  setVehicleTargets([vehicle('a', .001, 3000)], {}, 3000);
  near(rendered('a', 4000).lng, .001);
});

test('out-of-order telemetry does not reverse the marker', () => {
  setVehicleTargets([vehicle('a', 0, 0)], {}, 0);
  setVehicleTargets([vehicle('a', .001, 2000)], {}, 2000);
  setVehicleTargets([vehicle('a', -.001, 1000)], {}, 2500);
  near(rendered('a', 4000).lng, .001);
});

test('open route endpoint stays at the endpoint', () => {
  const shape = [position(0), position(.001)];
  setVehicleTargets([vehicle('a', 0, 0)], { a: shape }, 0);
  setVehicleTargets([vehicle('a', .001, 2000)], { a: shape }, 2000);
  near(rendered('a', 4000).lng, .001);
});

test('loop distances wrap consistently beyond multiple laps and below zero', () => {
  const geometry = getShapeGeometry([position(0), position(.001), position(.001, .001), position(0)]);
  const expected = pointAtDistance(geometry, 10).point;
  near(pointAtDistance(geometry, geometry.totalLength * 3 + 10).point.lng, expected.lng);
  near(pointAtDistance(geometry, -geometry.totalLength + 10).point.lng, expected.lng);
});

test('nearby return leg does not cause a trip around the entire route', () => {
  const shape = [position(0), position(.02), position(.02, .0001), position(0, .0001)];
  setVehicleTargets([vehicle('a', .001, 0)], { a: shape }, 0);
  setVehicleTargets([vehicle('a', .0011, 2000, .00009)], { a: shape }, 2000);
  const midpoint = rendered('a', 3000);
  near(midpoint.lng, .00105);
  near(midpoint.lat, 0);
});

test('entering a route preserves the current rendered location', () => {
  setVehicleTargets([vehicle('a', 0, 0, .001)], {}, 0);
  const shape = [position(0), position(.01)];
  setVehicleTargets([vehicle('a', .001, 2000)], { a: shape }, 2000);
  near(rendered('a', 2000).lat, .001);
  near(rendered('a', 4000).lat, 0);
});
