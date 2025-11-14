# Migration: Fix Cluster Centroid Type

**Issue**: cluster.centroid was created as `double precision[]` instead of `vector(512)`

**Fix Applied**:
```sql
ALTER TABLE cluster ALTER COLUMN centroid TYPE vector(512) USING centroid::vector(512);
```

**Also Added**: `metadata` column to cluster table
```sql
ALTER TABLE cluster ADD COLUMN metadata JSONB;
```

## To Make Permanent

Add this migration file:

```sql
-- migrations/versions/004_fix_cluster_centroid_type.py
ALTER TABLE cluster ALTER COLUMN centroid TYPE vector(512) USING centroid::vector(512);
ALTER TABLE cluster ADD COLUMN IF NOT EXISTS metadata JSONB;
```
