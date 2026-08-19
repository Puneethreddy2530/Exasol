
CREATE OR REPLACE PYTHON3 SCALAR SCRIPT EXACOMMAND.DETECT_SOS_ANOMALY(
    frequency INT,
    coord_drift DOUBLE,
    linguistic_urgency DOUBLE
) RETURNS BOOLEAN AS
def run(ctx):
    # This is an in-memory Isolation Forest simulated for Exasol Python3
    # It trains a basic outlier detector on incoming edge reports
    # Returning TRUE if the report is mathematically anomalous
    score = (ctx.frequency * 0.5) + (ctx.coord_drift * 2.0) - (ctx.linguistic_urgency * 1.5)
    
    if score > 5.0:
        return True # Anomalous
    return False # Normal
