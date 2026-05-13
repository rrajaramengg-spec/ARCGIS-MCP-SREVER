// ── Response Normalization Module ─────────────────
// Extracts renderable layer groups from backend
// response shapes: new typed results[] format and
// legacy (flat, spatial join, multi-result).
// Used by both map.js and chat.js.

/**
 * Infer ArcGIS geometry type from the first feature's geometry keys.
 */
function inferGeometryType(features) {
    if (!features || features.length === 0) return null;
    const geom = features[0]?.geometry;
    if (!geom) return null;
    if (geom.rings) return 'esriGeometryPolygon';
    if (geom.paths) return 'esriGeometryPolyline';
    if (geom.points) return 'esriGeometryMultipoint';
    if (geom.x !== undefined && geom.y !== undefined) return 'esriGeometryPoint';
    return null;
}

// ── New typed results[] format ────────────────────

/**
 * Convert a feature_set result entry to a renderable layer group.
 * Maps the `role` field to boolean flags for map.js symbol selection.
 */
function featureSetToLayer(r) {
    const features = Array.isArray(r.features) ? r.features : [];
    const role = r.role || 'result';
    return {
        name: r.layer || 'Query',
        features,
        geometryType: r.geometryType || inferGeometryType(features),
        fields: r.fields || [],
        spatialReference: r.spatialReference || null,
        role: role === 'buffer' ? 'parent' : role === 'source' ? 'parent' : 'child',
        count: r.count != null ? r.count : features.length,
        countOnly: features.length === 0 && r.count > 0 && r.geometryType == null,
        bufferZone: role === 'buffer',
        proximityLines: role === 'distance_line',
        sourceLocation: role === 'source',
    };
}

/**
 * Convert a geocode result entry to a renderable point layer.
 */
function geocodeToLayer(r) {
    const loc = r.location || {};
    return {
        name: r.address || 'Location',
        features: [{
            geometry: { x: loc.x, y: loc.y, spatialReference: { wkid: 4326 } },
            attributes: { address: r.address || '', score: r.score || 0 },
        }],
        geometryType: 'esriGeometryPoint',
        fields: [],
        spatialReference: { wkid: 4326 },
        role: 'parent',
        sourceLocation: true,
        count: 1,
    };
}

// ── Legacy format helpers ─────────────────────────

/**
 * Normalize a single query result into an array of layer groups.
 * Returns null only when no structural metadata exists.
 * Preserves zero-feature layers so chat can show accurate counts.
 */
function normalizeSingle(data) {
    if (!data || typeof data !== 'object') return null;
    if (data.error) return null;

    // Count-only response — preserve with count metadata
    if (data.type === 'count' && !Array.isArray(data.features)) {
        if (data.count != null) {
            return {
                layers: [{
                    name: data.layer || 'Query',
                    features: [],
                    geometryType: null,
                    fields: [],
                    spatialReference: null,
                    role: 'primary',
                    count: data.count,
                    countOnly: true,
                }],
            };
        }
        return null;
    }

    // Spatial join — parent + children
    if (data.type === 'spatial_join' && data.parent) {
        const layers = [];

        // Parent layer group — include even when features is empty
        const parentFeatures = Array.isArray(data.parent?.features) ? data.parent.features : [];
        layers.push({
            name: data.layer || 'Parent',
            features: parentFeatures,
            geometryType: data.parent.geometryType || inferGeometryType(parentFeatures),
            fields: data.parent.fields || [],
            spatialReference: data.parent.spatialReference,
            role: 'parent',
            count: data.parent.count != null ? data.parent.count : parentFeatures.length,
        });

        // Child layer groups — include even when features: []
        if (Array.isArray(data.children)) {
            for (const child of data.children) {
                const childFeatures = Array.isArray(child.features) ? child.features : [];
                layers.push({
                    name: child.layer || 'Child',
                    features: childFeatures,
                    geometryType: child.geometryType || inferGeometryType(childFeatures),
                    fields: child.fields || [],
                    spatialReference: child.spatialReference,
                    role: 'child',
                    count: child.count != null ? child.count : childFeatures.length,
                });
            }
        }

        return layers.length > 0 ? { layers } : null;
    }

    // Flat query with features (including empty feature arrays with metadata)
    if (Array.isArray(data.features)) {
        return {
            layers: [{
                name: data.layer || 'Query',
                features: data.features,
                geometryType: data.geometryType || inferGeometryType(data.features),
                fields: data.fields || [],
                spatialReference: data.spatialReference,
                role: 'primary',
                count: data.count != null ? data.count : data.features.length,
            }],
        };
    }

    // No structural metadata at all
    return null;
}

/**
 * Normalize a query response from the backend into renderable layer groups.
 *
 * Accepts either:
 * - Full ExecuteResponse with typed results[] (new format: entries have `type` field)
 * - Legacy `data` object (old format: `{source, results}` or flat features)
 *
 * @param {object} data - Full response or the `data` field from an ExecuteResponse
 * @returns {{ layers: Array<{name, features, geometryType, fields, spatialReference, role, count}> } | null}
 */
export function normalizeQueryResponse(data) {
    if (!data || typeof data !== 'object') return null;
    if (data.error) return null;

    // ── New typed results[] format ──
    // Detect via results[0].type (typed results always have a type field)
    if (Array.isArray(data.results) && data.results.length > 0 && data.results[0]?.type) {
        const layers = [];
        for (const r of data.results) {
            if (!r || typeof r !== 'object') continue;
            if (r.type === 'geocode') {
                layers.push(geocodeToLayer(r));
            } else if (r.type === 'feature_set') {
                layers.push(featureSetToLayer(r));
            }
        }
        return layers.length > 0 ? { layers } : null;
    }

    // ── Legacy: uniform response shape { source, results[] } ──
    if (data.source !== undefined && Array.isArray(data.results)) {
        const allLayers = [];

        // Source with features → parent layer
        if (data.source && data.source.features && Array.isArray(data.source.features)) {
            const sf = data.source.features;
            allLayers.push({
                name: data.source.layer || 'Source',
                features: sf,
                geometryType: inferGeometryType(sf),
                fields: [],
                spatialReference: null,
                role: 'parent',
                count: sf.length,
            });
        }

        // Source with location (geocode/coordinates) → synthetic pin marker
        if (data.source && data.source.location
            && (data.source.type === 'geocode' || data.source.type === 'coordinates' || data.source.type === 'reverse_geocode')
            && !(data.source.features && data.source.features.length > 0)) {
            const loc = data.source.location;
            allLayers.push({
                name: data.source.address || 'Location',
                features: [{
                    geometry: { x: loc.x, y: loc.y, spatialReference: { wkid: 4326 } },
                    attributes: { address: data.source.address || '', score: data.source.score || 0 },
                }],
                geometryType: 'esriGeometryPoint',
                fields: [],
                spatialReference: { wkid: 4326 },
                role: 'parent',
                sourceLocation: true,
                count: 1,
            });
        }

        // Results → child layers (buffer_zone gets parent role, proximity_lines gets line role)
        for (const result of data.results) {
            if (!result || typeof result !== 'object') continue;
            const features = Array.isArray(result.features) ? result.features : [];
            const isBufferZone = result.type === 'buffer_zone' || result.layer === '_buffer_zone';
            const isProximityLines = result.type === 'proximity_lines' || result.layer === '_proximity_lines';
            allLayers.push({
                name: result.layer || 'Result',
                features,
                geometryType: result.geometryType || inferGeometryType(features),
                fields: result.fields || [],
                spatialReference: result.spatialReference || null,
                role: isBufferZone ? 'parent' : 'child',
                count: result.count != null ? result.count : features.length,
                countOnly: result.type === 'count',
                joinType: result.join_type || null,
                totalInRadius: result.total_in_radius || null,
                searchRadius: result.search_radius || null,
                searchUnit: result.search_unit || null,
                bufferZone: isBufferZone,
                proximityLines: isProximityLines,
            });
        }

        return allLayers.length > 0 ? { layers: allLayers, source: data.source } : null;
    }

    // Multi-result wrapper (legacy)
    if (Array.isArray(data.results)) {
        const allLayers = [];
        for (const result of data.results) {
            const normalized = normalizeSingle(result);
            if (normalized) {
                allLayers.push(...normalized.layers);
            }
        }
        return allLayers.length > 0 ? { layers: allLayers } : null;
    }

    // Single result (legacy)
    return normalizeSingle(data);
}

/**
 * Extract graph execution metadata from a response, if present.
 * Returns null when no graph execution was used.
 *
 * @param {object} response - The full ExecuteResponse
 * @returns {{ nodes_executed: number, parallel_groups: number, retry_budget_used: number, errors: object, skipped: Array, node_timing: Array } | null}
 */
export function extractExecutionGraph(response) {
    if (!response || typeof response !== 'object') return null;
    return response.execution_graph || null;
}
