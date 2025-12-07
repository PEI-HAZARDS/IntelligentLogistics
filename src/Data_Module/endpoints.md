## Endpoints
### External
- POST: api/auth/login
- POST: api/auth/logout

- GET: api/arrivals                                 

- GET: api/arrivals/{gate_id}                       
- GET: api/arrivals/{gate_id}/{shift}                       
- GET: api/arrivals/{gate_id}/{shift}/total                

- GET: api/arrivals/{gate_id}/pending               
- GET: api/arrivals/{gate_id}/{shift}/pending               
- GET: api/arrivals/{gate_id}/{shift}/pending/total         

- GET: api/arrivals/{gate_id}/in_progress           
- GET: api/arrivals/{gate_id}/{shift}/in_progress           
- GET: api/arrivals/{gate_id}/{shift}/in_progress/total     

- GET: api/arrivals/{gate_id}/finished              
- GET: api/arrivals/{gate_id}/{shift}/finished              
- GET: api/arrivals/{gate_id}/{shift}/finished/total        

- GET: api/stream/{gate_id}/high
- GET: api/stream/{gate_id}/low

- PUT: api/manual_review/{gate_id}/{truck_id}/{decision}

- Listening on kafka topic (decision_made)

### Internal
- POST: api/decision/{gate_id}/{decision}
- GET: api/arrivals/{gate_id}/pending

### Notes:
- Chegadas estão associadas a turnos se um gajo chega mais cedo (noutro turno) o decision engine troca o turno na BD e ele vai aparecer no frontend como dauele turni

- Qual é o processo de tomada de decisão no decision engine tendo em conta as horas?

- GET para MinIO???