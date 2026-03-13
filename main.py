#!/usr/bin/env python3
"""
Gmail Expense Parser - Entry Point
"""
import sys
import argparse
import logging
from src.app import GmailExpenseParserApp


def main():
    """Main entry point for the Gmail Expense Parser."""
    # Canonical CLI entry point for the maintained application path.
    parser = argparse.ArgumentParser(description='Gmail Expense Parser')
    parser.add_argument(
        '--no-enhancements', 
        action='store_true', 
        help='Disable enhanced logging and progress indicators'
    )
    parser.add_argument(
        '--debug', 
        action='store_true', 
        help='Enable debug level logging'
    )
    parser.add_argument(
        '--date-from',
        type=str,
        default=None,
        help='Email start date (inclusive), format: YYYY-MM-DD'
    )
    parser.add_argument(
        '--date-to',
        type=str,
        default=None,
        help='Email end date (inclusive), format: YYYY-MM-DD'
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=4,
        help='Maximum number of parallel workers (default: 4)'
    )
    
    args = parser.parse_args()
    
    # Initialize and run the application
    app = GmailExpenseParserApp(use_enhancements=not args.no_enhancements)
    
    # Override log level if debug requested
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        # Also set for app logger
        app.logger.setLevel(logging.DEBUG)
    
    # Execute the pipeline
    stats = app.run(
        date_from=args.date_from,
        date_to=args.date_to,
        max_workers=args.workers
    )
    
    # Exit with appropriate status code
    if stats.get('errors', 0) > 0 and stats.get('receipts_parsed', 0) == 0:
        sys.exit(1)
    
    sys.exit(0)


if __name__ == '__main__':
    main()
