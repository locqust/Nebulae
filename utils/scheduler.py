# utils/scheduler.py
"""
Background scheduler for running periodic tasks within the Flask application.
Runs in a separate thread and doesn't require HTTP requests.
"""
import threading
import time
from datetime import datetime
from flask import current_app

class BackgroundScheduler:
    """Background scheduler that runs periodic tasks in a separate thread."""
    
    def __init__(self, app=None):
        self.app = app
        self.running = False
        self.thread = None
        
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize the scheduler with the Flask app."""
        self.app = app
    
    def start(self):
        """Start the background scheduler thread."""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.thread.start()
        print("Background scheduler started")
    
    def stop(self):
        """Stop the background scheduler thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        print("Background scheduler stopped")
    
    def _run_scheduler(self):
        """Main scheduler loop - runs in background thread."""
        # Wait for app to be fully initialized
        time.sleep(10)
        
        while self.running:
            try:
                # Run scheduled tasks within app context
                with self.app.app_context():
                    self._check_scheduled_backup()
                
                # Check every 5 minutes
                time.sleep(300)
                
            except Exception as e:
                print(f"Error in background scheduler: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(60)  # On error, wait 1 minute before retrying
    
    def _check_scheduled_backup(self):
        """Check if a scheduled backup should run and execute it."""
        try:
            from utils.backup_utils import (
                should_run_scheduled_backup, 
                create_backup, 
                update_last_backup_time, 
                cleanup_old_backups
            )
            
            if should_run_scheduled_backup():
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                print(f"[{current_time}] Starting scheduled backup...")
                
                success, message, _ = create_backup(is_scheduled=True)
                
                if success:
                    update_last_backup_time()
                    # Also cleanup old backups
                    deleted_count, cleanup_msg = cleanup_old_backups()
                    print(f"[{current_time}] Backup completed: {message}")
                    if deleted_count > 0:
                        print(f"[{current_time}] {cleanup_msg}")
                else:
                    print(f"[{current_time}] Backup failed: {message}")
                    
        except Exception as e:
            print(f"Error during scheduled backup: {e}")
            import traceback
            traceback.print_exc()


# Global scheduler instance
scheduler = BackgroundScheduler()