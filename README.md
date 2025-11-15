# SharePoint Client Script

This Python script allows you to interact with SharePoint document libraries using client credentials flow.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create a `.env` file with your credentials:
```bash
cp .env.example .env
# Edit .env with your actual values
```

## Usage

### Basic usage:
```bash
python sharepoint_client.py --site-url "https://your-tenant.sharepoint.com/sites/your-site" --library-name "Documents" --output results.json
```

### With custom output file:
```bash
python sharepoint_client.py --site-url "https://your-tenant.sharepoint.com/sites/your-site" --library-name "Documents" --output myfiles.json
```

## Environment Variables

The script expects these environment variables to be set:

- `TENANT_ID`: Your Azure AD tenant ID
- `CLIENT_ID`: Your registered app's client ID
- `CLIENT_SECRET`: Your registered app's client secret

## Output Format

The script will output JSON format like:

```json
{
  "files": [
    {
      "name": "Document1.docx",
      "url": "https://tenant.sharepoint.com/sites/site-name/library-name/Document1.docx"
    }
  ]
}
```

## Notes

- Make sure your Azure AD app has the correct permissions for SharePoint
- The script handles authentication automatically using the client credentials flow
- You can override the default library name with command line arguments
- The output will be saved to the file you specify with the `--output` argument

## Error Handling

The script includes proper error handling for common issues like:
- Authentication failures
- Missing environment variables
- API rate limits
- Network connectivity issues

## Example

```bash
python sharepoint_client.py --site-url "https://mycompany.sharepoint.com/sites/mysite" --library-name "Shared Documents" --output myfiles.json
```

This will authenticate with SharePoint and list all files in the specified document library, saving the results to `myfiles.json`.