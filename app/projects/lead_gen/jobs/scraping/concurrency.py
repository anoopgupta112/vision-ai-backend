import concurrent.futures
import threading

class LeadProcessor:
    def __init__(self, use_threads=True, max_threads=5):
        self.use_threads = use_threads
        self.executor = None
        if self.use_threads:
            self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_threads)
        
    def submit_lead(self, lead_data, processing_function):
        """
        Submit a lead to be processed.
        
        Args:
            lead_data: Data dictionary/object to pass to the function
            processing_function: Function to call with lead_data
        """
        if self.use_threads and self.executor:
            # Run in thread pool
            self.executor.submit(processing_function, lead_data)
        else:
            # Run synchronously
            processing_function(lead_data)
            
    def shutdown(self):
        """Shutdown the thread pool if it exists"""
        if self.executor:
            self.executor.shutdown(wait=True)
