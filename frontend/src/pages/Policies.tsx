import { Link } from 'react-router-dom'
import { PageHeading } from '@/components/Panel'

export function Policies({ privacy = false }: { privacy?: boolean }) {
  return <>
    <PageHeading title={privacy ? 'Privacy policy' : 'Terms of Use'} description="DefectVision Pro local academic application" />
    <article className="policy-document">
      {privacy ? <>
        <section><h2>Images and inspection records</h2>
          <p>The application sends uploaded images and sampled camera frames to the configured inspection API. Saved inspections store the original image, heatmap, overlay, prediction, score, category, model version, and timestamp on the API host. Records remain in its SQLite database until deleted.</p>
          <p>You can review and delete saved records in <Link to="/history">Inspection History</Link>. Downloaded PDFs and exported copies remain wherever you save them.</p>
        </section>
        <section><h2>Camera access</h2>
          <p>Live Inspection requests camera permission when you start the camera. While a category is selected and sampling is active, captured frames go to the inspection API. Preview frames use a temporary server cache with a five-minute expiry and a maximum of eight frames. Saving a selected frame creates a persistent inspection record. Stopping the camera or leaving the page releases camera tracks.</p>
        </section>
        <section><h2>Browser preferences and connections</h2>
          <p>The browser stores your reduced-motion preference in local storage. Inspection requests use the API address shown in <Link to="/settings">Settings</Link>. The configured API host receives those images and requests. Review that address before uploading confidential material.</p>
          <p>The current application uses local model inference. Its frontend includes no advertising or analytics tracking service. Operators who deploy the application manage server access, logs, storage, and any additional services they configure.</p>
        </section>
      </> : <>
        <section><h2>Academic use</h2>
          <p>DefectVision Pro supports academic demonstrations and visual inspection research. Use it with images you have permission to process, and comply with the licenses of any datasets you use.</p>
          <p>MVTec AD sample images carry their own attribution and noncommercial license terms. Keep the supplied license with any distributed sample images.</p>
        </section>
        <section><h2>Review of predictions</h2>
          <p>Predictions depend on the selected category, checkpoint, decision threshold, and image conditions. A human must verify automated predictions before a safety-critical manufacturing decision. The anomaly score measures model output and can vary across categories and versions.</p>
        </section>
        <section><h2>Local operation and data</h2>
          <p>The operator manages the API host, model files, saved images, and database backups. Deleting a saved inspection removes its record and associated media from the application. Keep required exports before deletion.</p>
          <p>Read the <Link to="/privacy">Privacy policy</Link> for details of image handling and browser preferences.</p>
        </section>
      </>}
    </article>
  </>
}
