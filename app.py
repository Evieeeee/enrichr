import os
import uuid
import json
import threading
import time
from datetime import datetime
from flask import Flask, request, jsonify, send_file, render_template
import anthropic
import pandas as pd
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
app.config['UPLOAD_FOLDER'] = '/tmp/uploads'
app.config['OUTPUT_FOLDER'] = '/tmp/outputs'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

# In-memory job store (use Redis/DB in production for multi-instance)
jobs = {}
jobs_lock = threading.Lock()


def get_anthropic_client():
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")
    return anthropic.Anthropic(api_key=api_key)


def update_job(job_id, **kwargs):
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id].update(kwargs)
            jobs[job_id]['updated_at'] = datetime.utcnow().isoformat()


def research_field_for_contact(client, contact: dict, field: dict) -> str:
    """Use Claude with web search to research a specific field for a contact."""
    system_prompt = """You are a professional business researcher. Your task is to research specific information about a person or company.
    
    Rules:
    - Return ONLY the requested information, nothing else
    - Be concise and factual
    - If information cannot be found, return "Not found"
    - Do not include explanations, caveats, or meta-commentary
    - Return a single value or short phrase unless the field description asks for more
    """

    user_prompt = f"""Research the following information:

Person: {contact.get('first_name', '')} {contact.get('last_name', '')}
Email: {contact.get('email', '')}
Company: {contact.get('company_name', '')}

Field to research: {field['name']}
Description/Instructions: {field['description']}

Return only the answer for "{field['name']}"."""

    try:
        # Use web search tool for deep research
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=500,
            system=system_prompt,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": user_prompt}]
        )

        # Extract text from response
        result_text = ""
        for block in response.content:
            if hasattr(block, 'text'):
                result_text += block.text

        return result_text.strip() if result_text.strip() else "Not found"

    except Exception as e:
        return f"Error: {str(e)[:100]}"


def process_enrichment_job(job_id: str, contacts: list, fields: list, output_path: str):
    """Background thread that processes the enrichment job."""
    try:
        client = get_anthropic_client()
        total_tasks = len(contacts) * len(fields)
        completed_tasks = 0

        update_job(job_id,
                   status='running',
                   total=total_tasks,
                   completed=0,
                   message='Starting enrichment...')

        # Build results: start with original contact data
        results = []
        for contact in contacts:
            row = {
                'email': contact.get('email', ''),
                'first_name': contact.get('first_name', ''),
                'last_name': contact.get('last_name', ''),
                'company_name': contact.get('company_name', ''),
            }
            results.append(row)

        # Process each contact x field combination
        for i, contact in enumerate(contacts):
            contact_name = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip() or contact.get('email', f'Row {i+1}')

            for j, field in enumerate(fields):
                update_job(job_id,
                           completed=completed_tasks,
                           message=f'Researching "{field["name"]}" for {contact_name}...',
                           current_contact=contact_name,
                           current_field=field['name'])

                value = research_field_for_contact(client, contact, field)
                results[i][field['name']] = value

                completed_tasks += 1
                update_job(job_id,
                           completed=completed_tasks,
                           progress_pct=round((completed_tasks / total_tasks) * 100, 1))

                # Small delay to avoid rate limiting
                time.sleep(0.5)

        # Write output Excel
        df = pd.DataFrame(results)
        df.to_excel(output_path, index=False)

        update_job(job_id,
                   status='complete',
                   completed=total_tasks,
                   progress_pct=100,
                   message='Enrichment complete! Your file is ready to download.',
                   output_ready=True)

    except Exception as e:
        update_job(job_id,
                   status='error',
                   message=f'Error: {str(e)}',
                   error=str(e))


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/start', methods=['POST'])
def start_job():
    """Start a new enrichment job."""
    try:
        # Handle file upload
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        # Parse fields from form data
        fields_json = request.form.get('fields', '[]')
        try:
            fields = json.loads(fields_json)
        except json.JSONDecodeError:
            return jsonify({'error': 'Invalid fields JSON'}), 400

        if not fields:
            return jsonify({'error': 'No enrichment fields specified'}), 400

        # Save uploaded file
        filename = secure_filename(file.filename)
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4()}_{filename}")
        file.save(upload_path)

        # Parse the uploaded file
        try:
            if filename.endswith('.csv'):
                df = pd.read_csv(upload_path)
            else:
                df = pd.read_excel(upload_path)
        except Exception as e:
            return jsonify({'error': f'Could not parse file: {str(e)}'}), 400

        # Validate required columns
        df.columns = [c.lower().strip().replace(' ', '_') for c in df.columns]
        required_cols = ['email']
        optional_cols = ['first_name', 'last_name', 'company_name']
        all_known_cols = required_cols + optional_cols
        missing = [c for c in all_known_cols if c not in df.columns]
        if missing:
            # Try fuzzy matching
            col_map = {}
            for req in all_known_cols:
                for col in df.columns:
                    if req.replace('_', '') in col.replace('_', '').replace(' ', ''):
                        col_map[col] = req
                        break
            if col_map:
                df = df.rename(columns=col_map)
                missing = [c for c in required_cols if c not in df.columns]

        if missing:
            return jsonify({
                'error': f'Missing required columns: {missing}. Found columns: {list(df.columns)}'
            }), 400

        # Include email plus any optional cols that are present
        cols_to_use = [c for c in all_known_cols if c in df.columns]
        contacts = df[cols_to_use].to_dict('records')

        # Create job
        job_id = str(uuid.uuid4())
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], f"enriched_{job_id}.xlsx")

        with jobs_lock:
            jobs[job_id] = {
                'id': job_id,
                'status': 'queued',
                'total': len(contacts) * len(fields),
                'completed': 0,
                'progress_pct': 0,
                'message': 'Job queued, starting soon...',
                'output_ready': False,
                'created_at': datetime.utcnow().isoformat(),
                'updated_at': datetime.utcnow().isoformat(),
                'contact_count': len(contacts),
                'field_count': len(fields),
                'output_path': output_path,
            }

        # Start background thread
        thread = threading.Thread(
            target=process_enrichment_job,
            args=(job_id, contacts, fields, output_path),
            daemon=True
        )
        thread.start()

        return jsonify({'job_id': job_id, 'message': 'Job started', 'total_tasks': len(contacts) * len(fields)})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/status/<job_id>')
def job_status(job_id):
    """Get the status of a job."""
    with jobs_lock:
        job = jobs.get(job_id)

    if not job:
        return jsonify({'error': 'Job not found'}), 404

    # Don't expose the file path
    safe_job = {k: v for k, v in job.items() if k != 'output_path'}
    return jsonify(safe_job)


@app.route('/api/download/<job_id>')
def download_result(job_id):
    """Download the enriched Excel file."""
    with jobs_lock:
        job = jobs.get(job_id)

    if not job:
        return jsonify({'error': 'Job not found'}), 404

    if not job.get('output_ready'):
        return jsonify({'error': 'File not ready yet'}), 400

    output_path = job.get('output_path')
    if not output_path or not os.path.exists(output_path):
        return jsonify({'error': 'Output file not found'}), 404

    return send_file(
        output_path,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'enriched_contacts_{job_id[:8]}.xlsx'
    )


@app.route('/health')
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
