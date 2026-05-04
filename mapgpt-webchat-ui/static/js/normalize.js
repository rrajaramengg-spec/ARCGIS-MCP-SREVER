// ── Response Normalization Module ─────────────────
// Extracts renderable layer groups from all backend
// response shapes (flat, spatial join, multi-result).
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
 * @param {object} data - The raw `data.data` from an ExecuteResponse
 * @returns {{ layers: Array<{name, features, geometryType, fields, spatialReference, role, count}> } | null}
 */
export function normalizeQueryResponse(data) {
    if (!data || typeof data !== 'object') return null;
    if (data.error) return null;

    // Uniform response shape: { source, results[] }
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
                count: 1,
            });
        }

        // Results → child layers (buffer_zone gets parent role)
        for (const result of data.results) {
            if (!result || typeof result !== 'object') continue;
            const features = Array.isArray(result.features) ? result.features : [];
            const isBufferZone = result.type === 'buffer_zone' || result.layer === '_buffer_zone';
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
