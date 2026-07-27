import sys
import os

from app.system.system_metrics import get_performance_metrics_snapshot

print(get_performance_metrics_snapshot())
